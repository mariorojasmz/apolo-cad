"""Lo que la persona VE del tablero armado (plan V8.5 D13, D15; F3b): la ÚNICA fuente del panel
«Tablero» del visor (`GET /api/tablero/{ubicacion}`) y de `get_circuit tablero=true`, así el agente
y la persona leen lo mismo. El llamador sostiene `STATE_LOCK`.

Sale de `tablero.ruteos` (el armado recalculado y su ruteo) y de los SELECTORES de
`tablero_reglas.py` (los mismos que el ERC): aquí no se decide ninguna regla, sólo se cuenta en
palabras de la persona (sin nombres de comandos ni parámetros: ui/CLAUDE.md § Texto) y se señala
DÓNDE (los ids de las piezas que encuadra la cámara).

- `veredicto`: UNO, con la regla de `ui/src/diseno/atencion.ts::veredictoDe` («El tablero
  cumple»; si no, cuántas cosas corregir y revisar; lo «sin evaluar» sólo da la frase si no hay
  nada más).
- `items`: lo que pide atención, cada uno con su frase, su cifra (`valor` + `unidad`: la UI la
  escribe con `cifra()`), las piezas que señala y los conductores que toca. Un hallazgo que se
  repite por conductor (largo a mano que no cuadra, conductor que sale sin cable) es UN ítem con
  la cuenta: el detalle los lista.
- `puerta`: la junta de D5 que mueve el deslizador, con lo que revisó el executor.
- `detalle`: lo que está bien (`bien`), aparatos, canaletas con su llenado, conductores con su
  largo y, con `recorridos`, su recorrido en coordenadas de MUNDO (mm; una polilínea por tramo,
  con la puerta cerrada); el calentamiento SIN EVALUAR (F3 espera las curvas de IEC/TR 60890:
  nunca un número inventado) con las pérdidas declaradas, que sí son dato.
"""

from __future__ import annotations

from .errors import ServiceError
from .tablero import LAYOUT, layouts, pieza_canaleta, ruteos

FRASE_BIEN = "El tablero cumple"
#: lo único que queda es «sin evaluar» (el calentamiento, hasta F3): cumple lo que se revisó
FRASE_PARCIAL = "El tablero cumple lo que revisamos"
MOTIVO_CALOR = "Todavía no lo calculamos: falta la norma IEC/TR 60890. No damos una cifra estimada."
NBSP = " "  # entre una cifra y su unidad: la línea no los separa
PESO = {"falla": 0, "aviso": 1, "sin_evaluar": 2, "bien": 3}


def _u(texto) -> str:
    t = str(texto or "").strip()
    return f"+{t}" if t and not t.startswith("+") else t


def veredicto(items: list[dict], frase_bien: str = FRASE_BIEN, frase_parcial: str = FRASE_PARCIAL) -> dict:
    """La misma regla que `veredictoDe` (atencion.ts): la severidad es la del ítem más grave; lo
    sin evaluar no cuenta, y si es lo único, cumple lo que se revisó (no «cumple» a secas)."""
    atender = sorted((it for it in items if it["severidad"] != "bien"), key=lambda it: PESO[it["severidad"]])
    if not atender:
        return {"severidad": "bien", "frase": frase_bien}
    if all(it["severidad"] == "sin_evaluar" for it in atender):
        return {"severidad": "bien", "frase": frase_parcial}

    def cosas(n: int) -> str:
        return f"{n} {'cosa' if n == 1 else 'cosas'}"

    f, a = (sum(1 for it in atender if it["severidad"] == k) for k in ("falla", "aviso"))
    sev = atender[0]["severidad"]
    if f and a:
        return {"severidad": sev, "frase": f"{cosas(f)} por corregir y {a} por revisar"}
    if f:
        return {"severidad": sev, "frase": f"{cosas(f)} por corregir"}
    return {"severidad": sev, "frase": f"{cosas(a)} por revisar"}


def tableros(doc) -> list[dict]:
    """[{ubicacion, comando, armado}] de cada `layout_tablero` del log: los vivos y los que una
    carga tolerante suprimió (`armado: false`, con su motivo en el panel)."""
    vivos = [{"ubicacion": u, "comando": cid, "armado": True} for cid, u in layouts(doc)]
    vistos = {t["comando"] for t in vivos}
    por_id = {c["id"]: c for c in doc.commands}
    rotos = [{"ubicacion": _u((por_id[s["command_id"]].get("params") or {}).get("ubicacion")),
              "comando": s["command_id"], "armado": False}
             for s in getattr(doc, "regen_suppressed", []) or []
             if s.get("type") == LAYOUT and s.get("command_id") in por_id and s["command_id"] not in vistos]
    return vivos + rotos


# ── cómo se dice ──────────────────────────────────────────────────────────────────────────


def _plural(n: int, uno: str, varios: str) -> str:
    return uno if n == 1 else varios


def nombre_canaleta(lay, i: int) -> str:
    """«la canaleta de arriba», «la de la izquierda», «la horizontal 2 desde arriba»: por su
    posición en la placa, que es lo que la persona ve."""
    k = lay.canaletas[i]
    mismas = [j for j, x in enumerate(lay.canaletas) if x.orientacion == k.orientacion]
    if k.orientacion == "h":
        orden = sorted(mismas, key=lambda j: -(lay.canaletas[j].v0 + lay.canaletas[j].v1))
        pos = orden.index(i)
        if len(orden) == 1 or pos == 0:
            return "canaleta de arriba"
        return "canaleta de abajo" if pos == len(orden) - 1 else f"canaleta horizontal {pos + 1} desde arriba"
    orden = sorted(mismas, key=lambda j: lay.canaletas[j].u0 + lay.canaletas[j].u1)
    pos = orden.index(i)
    if pos == 0:
        return "canaleta de la izquierda"
    return "canaleta de la derecha" if pos == len(orden) - 1 else f"canaleta vertical {pos + 1} desde la izquierda"


# ── las piezas que se señalan ─────────────────────────────────────────────────────────────


def _extremos(r, piezas: dict[str, str]) -> list[str]:
    out = []
    for p in r.puntos:
        fid = piezas.get(p.rsplit(":", 1)[0])
        if fid and fid not in out:
            out.append(fid)
    return out


def _a_mundo(t):
    """El punto (u, v, w) del ruteo → mundo: G con `armado.punto_g` y luego la matriz del gabinete."""
    from apolo.kernel.matrix import compose_place
    from apolo.library.electrico.armado import punto_g

    mm = compose_place(t.params.position.tuple(), t.params.rotation.tuple())

    def f(u: float, v: float, w: float) -> list[float]:
        g = (*punto_g(t.armado.interior, u, v, w), 1.0)
        return [round(sum(mm[i][k] * g[k] for k in range(4)), 1) for i in range(3)]
    return f


# ── el panel ──────────────────────────────────────────────────────────────────────────────


def _item(clave, severidad, frase, *, valor=None, unidad="", decimales=0, piezas=(), conductores=(),
          detalle=None, tecnico=None) -> dict:
    """`detalle`: una frase para la persona; `tecnico`: el texto crudo (va plegado en la UI)."""
    return {"clave": clave, "severidad": severidad, "frase": frase,
            **({"valor": valor, "unidad": unidad, "decimales": decimales} if valor is not None else {}),
            "piezas": list(piezas), "conductores": list(conductores), **({"detalle": detalle} if detalle else {}),
            **({"tecnico": tecnico} if tecnico else {})}


def _items(doc, t, piezas: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """(lo que pide atención, lo que está bien) del tablero `t`."""
    from .tablero_reglas import declarados_que_no_cuadran, llenas, salen_sin_cable

    atender, bien = [], []
    cid, tope = t.cid, t.ruteo.criterio["llenado_tope"]
    rec = (doc.joints.get(f"{cid}_puerta") or {}).get("recorrido") or {}
    puerta = [f"{cid}_puerta"]
    if rec.get("choques"):
        atender.append(_item("puerta", "falla", "La puerta choca al abrir", valor=rec["choques"], piezas=puerta))
    else:
        bien.append(_item("puerta", "bien", "La puerta abre sin chocar", valor=rec.get("a_deg", 110.0),
                          unidad="°", piezas=puerta,
                          detalle=f"Revisamos {rec.get('angulos_revisados', 0)} ángulos de su recorrido."))
    for ll in llenas(t):
        nombre = nombre_canaleta(t.layout, ll.canaleta)
        no_entran = ll.fraccion > 1.0
        atender.append(_item(
            f"canaleta-{ll.canaleta}", "falla" if no_entran else "aviso",
            f"Los conductores no entran en la {nombre}" if no_entran else f"La {nombre} va muy llena",
            valor=round(ll.fraccion * 100), unidad="%", piezas=[t.canaletas.get(ll.canaleta)] if
            t.canaletas.get(ll.canaleta) else [], conductores=ll.conductores,
            detalle=(f"{ll.ocupado_mm2:.0f} de {ll.util_mm2:.0f} mm² con {len(ll.conductores)} "
                     f"conductores; el tope es {tope * 100:.0f} %.")))
    if t.ruteo.llenados and not llenas(t):
        peor = max(t.ruteo.llenados, key=lambda x: x.fraccion)
        bien.append(_item("canaletas", "bien", "La canaleta más llena", valor=round(peor.fraccion * 100),
                          unidad="%", piezas=[t.canaletas[peor.canaleta]] if t.canaletas.get(peor.canaleta) else [],
                          detalle=f"Es la {nombre_canaleta(t.layout, peor.canaleta)}; el tope es {tope * 100:.0f} %."))
    malos = declarados_que_no_cuadran(t)
    if malos:
        rutas = [r for r, _ in malos]
        atender.append(_item(
            "largos", "aviso", _plural(len(rutas), "Conductor con un largo puesto a mano que no cuadra con su recorrido",
                                       "Conductores con un largo puesto a mano que no cuadra con su recorrido"),
            valor=len(rutas),
            piezas=sorted({f for r in rutas for f in _extremos(r, piezas)}), conductores=[r.id for r in rutas],
            detalle="La BOM compra el largo puesto a mano. Si nadie lo midió, pídele al agente que lo quite."))
    sueltos = salen_sin_cable(t)
    if sueltos:
        atender.append(_item(
            "sin-cable", "aviso", _plural(len(sueltos), "Conductor que sale del tablero sin ir dentro de un cable",
                                          "Conductores que salen del tablero sin ir dentro de un cable"),
            valor=len(sueltos),
            piezas=sorted({f for r in sueltos for f in _extremos(r, piezas)}), conductores=[r.id for r in sueltos],
            detalle="Afuera del tablero un conductor suelto no está protegido: pídele al agente que lo lleve "
                    "dentro de un cable."))
    atender.append(_item("calentamiento", "sin_evaluar", "Falta evaluar el calentamiento", detalle=MOTIVO_CALOR,
                         piezas=[f"{cid}_gabinete"]))
    total = sum(r.largo_mm for r in t.ruteo.rutas) / 1000.0
    if t.ruteo.rutas:
        bien.append(_item("largo", "bien", "Conductores dentro del tablero", valor=round(total, 1), unidad="m",
                          decimales=1, detalle=f"{len(t.ruteo.rutas)} conductores con su recorrido por las canaletas."))
    return atender, bien


def _calentamiento(m, u: str) -> dict:
    from apolo.library.catalog import CATALOG

    total, sin_dato = 0.0, []
    for d in m.dispositivos:
        if d.ubicacion != u:
            continue
        comp = CATALOG.get(d.ref)
        e = comp.electrico if comp is not None else None
        if e is None or e.simbolo == "gabinete":
            continue
        if e.perdidas_W is None:
            sin_dato.append(d.designacion)
        else:
            total += float(e.perdidas_W) * int(d.cantidad or 1)
    return {"estado": "sin_evaluar", "motivo": MOTIVO_CALOR, "perdidas_W": round(total, 1),
            "sin_dato": sin_dato}


def _conductor(r, piezas, mundo) -> dict:
    return {"id": r.id, "puntos": list(r.puntos), "largo_m": round(r.usado_mm / 1000.0, 3), "origen": r.origen,
            "ruteado_m": round(r.largo_mm / 1000.0, 3),
            **({"declarado_m": round(r.declarado_mm / 1000.0, 3)} if r.declarado_mm is not None else {}),
            **({"sale": True} if r.sale else {}), **({"cable": r.cable} if r.cable else {}),
            "piezas": _extremos(r, piezas),
            **({"recorrido": [x for x in (_polilinea(s.recorrido, mundo) for s in r.segmentos) if len(x) > 1]}
               if mundo else {})}


def _polilinea(puntos, mundo) -> list[list[float]]:
    """Los puntos del tramo en el mundo, sin repetir uno seguido (el ruteo repite las uniones)."""
    out: list[list[float]] = []
    for p in puntos:
        q = mundo(*p)
        if not out or max(abs(a - b) for a, b in zip(q, out[-1])) > 0.05:
            out.append(q)
    return out


def _canaletas(t) -> list[dict]:
    por = {ll.canaleta: ll for ll in t.ruteo.llenados}
    out = []
    for i, k in enumerate(t.layout.canaletas):
        ll = por.get(i)
        a, b = (k.u0, k.u1) if k.orientacion == "h" else (k.v0, k.v1)
        fid = t.canaletas.get(i) or pieza_canaleta(t.cid, t.armado, k, a, b)
        out.append({"nombre": nombre_canaleta(t.layout, i).capitalize(), "pieza": fid,
                    "orientacion": k.orientacion, "llenado": round(ll.fraccion, 3) if ll else 0.0,
                    "ocupado_mm2": ll.ocupado_mm2 if ll else 0.0,
                    "util_mm2": ll.util_mm2 if ll else None, "conductores": len(ll.conductores) if ll else 0})
    return out


def _sin_armar(doc, u: str, cid: str) -> dict:
    motivo = next((s.get("error") for s in getattr(doc, "regen_suppressed", []) or []
                   if s.get("command_id") == cid), None)
    items = [_item("armado", "falla", "El tablero no se pudo armar",
                   detalle="Pídele al agente que revise el armado del tablero.", tecnico=motivo or None)]
    v = {"severidad": "falla", "frase": "No se pudo armar el tablero",
         "nota": "Pídele al agente que lo revise; el motivo está en el detalle técnico."}
    return {"ubicacion": u, "comando": cid, "armado": False, "veredicto": v, "items": items}


def panel(doc, ubicacion: str, *, recorridos: bool = True) -> dict:
    """El panel de UN tablero (su ubicación, con o sin «+»). 404 con las válidas si no hay."""
    from apolo.library.catalog import CATALOG

    from .electrico import modelo
    from .tablero import dibujados

    u = _u(ubicacion)
    lista = tableros(doc)
    fila = next((x for x in lista if x["ubicacion"] == u), None)
    if fila is None:
        validas = ", ".join(x["ubicacion"] for x in lista) or "ninguno: pídele al agente que lo arme"
        raise ServiceError(404, f"No hay tablero armado en {u or '(sin ubicación)'}. Tableros: {validas}.")
    if not fila["armado"]:
        return _sin_armar(doc, u, fila["comando"])
    m = modelo(doc)
    t = next(x for x in ruteos(doc, m) if x.cid == fila["comando"])
    piezas = {d.designacion: d.pieza for d in m.dispositivos if d.ubicacion == u and d.pieza}
    piezas.update({k: v for k, v in dibujados(doc, m).items() if k not in piezas})
    atender, bien = _items(doc, t, piezas)
    i = t.armado.interior
    comp = CATALOG.get(t.layout.gabinete)
    mundo = _a_mundo(t) if recorridos else None
    v = veredicto(atender)
    v["nota"] = (f"Gabinete de {i.ancho:g}{NBSP}×{NBSP}{i.alto:g}{NBSP}mm · {len(t.layout.aparatos)}{NBSP}aparatos · "
                 f"{len(t.ruteo.rutas)}{NBSP}conductores")
    rec = (doc.joints.get(f"{t.cid}_puerta") or {})
    return {
        "ubicacion": u, "comando": t.cid, "armado": True,
        "gabinete": {"ref": t.layout.gabinete, "nombre": comp.name if comp else t.layout.gabinete,
                     "pieza": f"{t.cid}_gabinete", "medidas_mm": [i.ancho, i.fondo, i.alto]},
        "veredicto": v,
        "items": sorted(atender, key=lambda it: PESO[it["severidad"]]),
        "puerta": {"junta": f"{t.cid}_puerta", "pieza": f"{t.cid}_puerta", "min_deg": float(rec.get("lower", 0.0)),
                   "max_deg": float(rec.get("upper", 110.0)), "bisagra": i.bisagra},
        "detalle": {
            "bien": bien,
            "aparatos": [{"designacion": a.designacion, "ref": a.ref,
                          "nombre": CATALOG[a.ref].name if CATALOG.get(a.ref) else a.ref,
                          "zona": a.zona, "fila": a.fila, **({"pieza": piezas[a.designacion]}
                                                             if a.designacion in piezas else {})}
                         for a in t.layout.aparatos],
            "canaletas": _canaletas(t),
            "conductores": [_conductor(r, piezas, mundo) for r in t.ruteo.rutas],
            "calentamiento": _calentamiento(m, u),
            "supuestos": list(t.supuestos) + list(t.ruteo.avisos),
        },
    }


def paneles(doc, *, recorridos: bool = False) -> list[dict]:
    """El panel de cada tablero del documento (para `get_circuit tablero=true`: sin recorridos)."""
    return [panel(doc, x["ubicacion"], recorridos=recorridos) for x in tableros(doc)]
