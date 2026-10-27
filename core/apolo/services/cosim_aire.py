"""El circuito de AIRE del documento → lo que la co-simulación necesita (plan V8.9 F3, D3, D4, D8).

`cosim/` no importa el catálogo ni `library` (el worker no carga OCP), así que la traducción del
lado de aire del carril (`Dispositivo.neumatico`, `ModeloElectrico.tubos`) vive aquí, como la del
eléctrico en `cosim_red.py`:
  - `dispositivos(doc, me, cilindros)`: los `DispositivoCosim` del tablero con la ficha neumática
    PLANA en `modelo["aire"]` (puertos fuera; caudal como {C, b, m}) y, en cada cilindro, la
    `carrera_mm` de su junta en 3D (la de `acoples.cilindros`, o la del `{cmd}_vastago` de la
    pieza ligada, o la del `servicio`) y, en un bloqueo de vástago, el `cilindro` cuyo
    `servicio.bloqueo` lo nombra (plan bloqueo-de-vastago D2);
  - `red_aire(me, esc)`: {presion_red_bar, tubos} (el Ø interior y el largo de cada tubo); con
    aire y sin `condiciones.presion_red_bar` es 400 con el ejemplo (D3: la toma es una fuente a la
    presión que se DECLARA, nunca un default);
  - `peticion(doc, esc, tab)`: el `<motor>` de FUERZA de cada cilindro sobre su junta prismática y
    sus opciones de junta (la fricción de los sellos como `frictionloss` y, sólo si el vástago no
    pesa ya la masa móvil de su ficha —el de `create_pneumatic_cylinder` la pesa entera, plan
    pedidos-de-extensiones-iii D11—, la masa móvil en carrera 0 como armadura: el pistón no está
    en 3D), validando `acoples.cilindros` (un
    cilindro sin acople es 400 con el ejemplo listo para copiar, D8);
  - `acoples(esc, dyn, n_motores)`: `AcopleCilindro` y `AcopleReed` contra la dinámica preparada.
Todo error es `ServiceError(400, texto)`. Sin locks: el llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

import json

from .errors import ServiceError


def hay_aire(me) -> bool:
    return any(getattr(d, "neumatico", None) is not None for d in me.dispositivos)


def ficha_plana(f) -> dict:
    """La `FichaNeumatica` como dict JSON puro para `cosim` (sin puertos ni textos de fuente)."""
    out = dict(f.modelo)
    for nombre, c in (("caudal", f.caudal), ("escape", f.escape)):
        if c is not None:
            out[nombre] = {"C": float(c.C), "b": float(c.b), "m": float(c.m)}
    return json.loads(json.dumps(out, default=str))


def _junta_de_pieza(doc, d) -> str | None:
    """La junta del vástago del cilindro 3D ligado (`create_pneumatic_cylinder`: `{cmd}_cuerpo`)."""
    pieza = getattr(d, "pieza", None) or ""
    if pieza.endswith("_cuerpo"):
        j = pieza[: -len("_cuerpo")] + "_vastago"
        if j in (doc.joints or {}):
            return j
    return None


def _carrera(doc, d, junta: str | None) -> float | None:
    j = (doc.joints or {}).get(junta or _junta_de_pieza(doc, d) or "")
    if j is not None and j.get("type") == "prismatica":
        return float(j["upper"]) - float(j["lower"])
    c = (getattr(d, "servicio", None) or {}).get("carrera_mm")
    return float(c) if c is not None else None


def dispositivos(doc, me, cilindros: dict | None = None) -> list:
    """Los `DispositivoCosim` del tablero, con el aire de cada aparato en `modelo["aire"]`."""
    from apolo.cosim.datos import DispositivoCosim

    from .cosim_snapshot import _color, _plano

    out = []
    #: bloqueo → el cilindro que lo declara en `servicio.bloqueo` (plan bloqueo-de-vastago D2)
    muerde = {(getattr(d, "servicio", None) or {}).get("bloqueo"): d.designacion for d in me.dispositivos
              if (getattr(d, "servicio", None) or {}).get("bloqueo")}
    for d in me.dispositivos:
        modelo = _plano(d.modelo or {})
        if getattr(d, "neumatico", None) is not None:
            aire = ficha_plana(d.neumatico)
            if aire.get("tipo") == "cilindro":
                carrera = _carrera(doc, d, (cilindros or {}).get(d.designacion, {}).get("junta"))
                if carrera is not None:
                    aire["carrera_mm"] = carrera
            elif aire.get("tipo") == "bloqueo_vastago" and d.designacion in muerde:
                aire["cilindro"] = muerde[d.designacion]
            modelo["aire"] = aire
        out.append(DispositivoCosim(d.designacion, d.ref, modelo, _plano(d.ajustes or {}), int(d.cantidad or 1),
                                    d.pieza or None, _color(d.ref)))
    return out


def red_aire(me, esc) -> dict:
    """{presion_red_bar, tubos} o {} sin aire."""
    if not hay_aire(me):
        return {}
    if esc.presion_red_bar is None:
        raise ServiceError(400, "el documento tiene circuito de aire: declara la presión de la toma de la "
                                "máquina en el escenario, condiciones.presion_red_bar (bar manométricos), p. ej. "
                                '{"condiciones": {"presion_red_bar": 6}} (plan V8.9 D3: la red de planta no se '
                                "modela; la toma es una fuente a la presión que se declara)")
    tubos = [{"desde": t.desde, "hasta": t.hasta, "D_int_mm": t.D_int_mm, "largo_m": t.largo_m}
             for t in me.tubos]
    return json.loads(json.dumps({"presion_red_bar": float(esc.presion_red_bar), "tubos": tubos}))


def _sugerida(doc, me, des: str) -> str:
    d = next((x for x in me.dispositivos if x.designacion == des), None)
    j = _junta_de_pieza(doc, d) if d is not None else None
    if j:
        return j
    prism = sorted(n for n, j in (doc.joints or {}).items() if j.get("type") == "prismatica")
    return prism[0] if len(prism) == 1 else "<cmd>_vastago"


def exigir_acoples(doc, me, esc) -> None:
    """Cada cilindro del circuito, acoplado a la junta prismática de su vástago (D8: explícito,
    como el motor); cada acople, de un cilindro."""
    cils = [d.designacion for d in me.dispositivos
            if getattr(d, "neumatico", None) is not None and d.neumatico.tipo == "cilindro"]
    for des in cils:
        if des not in esc.cilindros:
            raise ServiceError(400, f"el cilindro {des} no está acoplado a la junta de su vástago: declara "
                                    f'acoples.cilindros = {{"{des}": {{"junta": "{_sugerida(doc, me, des)}"}}}} '
                                    "en el escenario (plan V8.9 D8)")
    for des, a in esc.cilindros.items():
        if des not in cils:
            raise ServiceError(400, f"acoples.cilindros: «{des}» no es un cilindro del circuito de aire; cilindros: "
                                    f"{', '.join(cils) or 'ninguno'}")
        j = (doc.joints or {}).get(a["junta"])
        if j is None or j.get("type") != "prismatica":
            raise ServiceError(400, f"acoples.cilindros.{des}: «{a['junta']}» no es una junta prismática del "
                                    f"documento (la del vástago de create_pneumatic_cylinder: "
                                    f"«{_sugerida(doc, me, des)}»)")


def peticion(doc, me, esc, tab) -> tuple[list[dict], dict]:
    """([motor de fuerza de cada cilindro], {junta: opciones}) para la petición de la dinámica
    (los acoples ya pasaron `exigir_acoples`)."""
    from apolo.physics.dinamica_cuerpos import masas_de_ficha

    motores, juntas = [], {}
    con_ficha = masas_de_ficha(doc.scene) if esc.cilindros else {}
    for des, a in esc.cilindros.items():
        m = tab.modelos[des]
        j = doc.joints[a["junta"]]
        motores.append({"junta": a["junta"], "modo": "par", "valor": 0.0,
                        "direccion_transporte": [float(c) for c in j["axis"]]})
        op = dict((esc.mecanica.get("juntas") or {}).get(a["junta"]) or {})
        op["friccion"] = float(op.get("friccion", 0.0)) + float(m.friccion_junta_N)
        if j.get("child") not in con_ficha:  # pedidos-iii D11: si no, el vástago ya la pesa
            op["armadura"] = float(op.get("armadura", 0.0)) + float(m.masa_base)
        juntas[a["junta"]] = op
    return motores, juntas


def acoples(esc, dyn, n_motores: int) -> tuple[list, list]:
    """(AcopleCilindro, AcopleReed) contra la dinámica preparada (sus actuadores van después de
    los de los motores eléctricos, en el orden de `acoples.cilindros`)."""
    from apolo.cosim.datos import AcopleCilindro, AcopleReed

    cils = [AcopleCilindro(des, a["junta"], md.nombre)
            for (des, a), md in zip(esc.cilindros.items(), dyn.motores[n_motores:])]
    reeds = []
    for des, s in esc.sensores.items():
        if "junta" not in s:
            continue
        j = dyn.juntas.get(s["junta"])
        if j is None or j["tipo"] != "prismatica":
            raise ServiceError(400, f"acoples.sensores.{des}: «{s['junta']}» no es una junta prismática de la "
                                    f"simulación; prismáticas: "
                                    f"{', '.join(n for n, x in dyn.juntas.items() if x['tipo'] == 'prismatica') or 'ninguna'}")
        reeds.append(AcopleReed(des, s["junta"], float(s["en_mm"]), float(s["ventana_mm"])))
    return cils, reeds
