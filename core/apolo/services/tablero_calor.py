"""El calentamiento de cada tablero armado (plan V8.5 D6, F3), leído del documento. El llamador
sostiene `STATE_LOCK`.

Arma lo que piden `library/electrico/calentamiento.py` (las reglas) e `iec60890.py` (el método):
- la ENVOLVENTE: la caja del gabinete del catálogo (alto × ancho × fondo) y sus caras CUBIERTAS
  (`caras_cubiertas`, decisión de F3, vetable): el FONDO siempre (el plan arma gabinetes de pared:
  su fondo va contra su soporte, T4 «rear side of wall-mounted enclosures»); el TECHO y cada
  LATERAL, si una pieza de la escena (no del layout) tapa al menos `FRACCION_CUBIERTA` de la cara a
  menos de `HOLGURA_CUBIERTA_MM` (criterio de diseño: a esa distancia el aire no circula); el
  frente es la puerta (libre) y el piso no cuenta (b = 0). Sin aberturas: los gabinetes del
  catálogo son cerrados (IP54/IP66);
- las PÉRDIDAS: Σ `perdidas_W` de los aparatos de la ubicación (los que no la traen se listan y
  cuentan 0) + I²R de cada conductor ruteado con la corriente de la regla 3 (por los aparatos que
  une, en el modelo eléctrico);
- cada APARATO con la altura de su borde superior (la caja del `Armado`) y el `T_max_C` de su
  ficha (`electrico.datos`); los conductores, con el `T_max_C` más bajo de sus refs, arriba;
- el AMBIENTE: `ambiente_C` del layout (35 °C si el comando no lo da: la referencia del método);
- si se pasa, además de la ventilación (`calentamiento.Sugerencia`), el GABINETE SIGUIENTE del
  catálogo donde el layout entra (`tablero.plan_con_gabinete`) y no se pasa, con las mismas
  pérdidas y las mismas caras cubiertas.

`evaluaciones(doc, tableros)` → {cid: dict}: lo que publican el panel (`tablero_panel.py`) y el
ERC (`reglas`): una sola cuenta.
"""

from __future__ import annotations

import math

#: criterio de diseño (F3): una cara está cubierta si algo la tapa en ≥ 50 % a ≤ 50 mm
HOLGURA_CUBIERTA_MM = 50.0
FRACCION_CUBIERTA = 0.5
_MUESTRAS = 20  # cuadrícula de muestreo de cada cara
NORMA = "IEC 60890:1987 (método tabulado por ABB SACE, Electrical installation handbook Vol. 1, Annex B)"


# ── las caras cubiertas ───────────────────────────────────────────────────────────────────


def _cajas_g(doc, t, excluir: set[str]) -> list[tuple]:
    """Las cajas (en el marco G del gabinete) de las piezas de la escena cercanas al gabinete."""
    from apolo.kernel.matrix import compose_place, invert_rigid

    i = t.armado.interior
    m = compose_place(t.params.position.tuple(), t.params.rotation.tuple())
    inv = invert_rigid(m)
    W, D, H = i.ancho, i.fondo, i.alto
    g = HOLGURA_CUBIERTA_MM
    out = []
    for fid, f in doc.scene.items():
        if fid in excluir or getattr(f, "is_guide", False) or f.shape is None:
            continue
        bb = f.shape.bounding_box()
        esquinas = [(x, y, z) for x in (bb.min.X, bb.max.X) for y in (bb.min.Y, bb.max.Y)
                    for z in (bb.min.Z, bb.max.Z)]
        loc = [tuple(sum(inv[r][k] * p[k] for k in range(3)) + inv[r][3] for r in range(3)) for p in esquinas]
        lo = tuple(min(p[k] for p in loc) for k in range(3))
        hi = tuple(max(p[k] for p in loc) for k in range(3))
        if hi[0] < -W / 2 - g or lo[0] > W / 2 + g or hi[1] < -D / 2 - g or lo[1] > D / 2 + g \
                or hi[2] < -H / 2 - g or lo[2] > H / 2 + g:
            continue
        out.append((fid, lo, hi))
    return out


def _cubre(cajas, eje: int, signo: int, borde: float, a: tuple, b: tuple, ejes_ab: tuple) -> tuple[float, list]:
    """(fracción de la cara tapada, ids que la tapan): cara ⊥ `eje` en `borde`, del lado `signo`."""
    g = HOLGURA_CUBIERTA_MM
    cerca = []
    for fid, lo, hi in cajas:
        if signo > 0 and borde - 1.0 <= lo[eje] <= borde + g:
            cerca.append((fid, lo, hi))
        elif signo < 0 and borde - g <= hi[eje] <= borde + 1.0:
            cerca.append((fid, lo, hi))
    if not cerca:
        return 0.0, []
    n, tapados, ids = _MUESTRAS, 0, set()
    ea, eb = ejes_ab
    for ia in range(n):
        pa = a[0] + (ia + 0.5) * (a[1] - a[0]) / n
        for ib in range(n):
            pb = b[0] + (ib + 0.5) * (b[1] - b[0]) / n
            hit = [fid for fid, lo, hi in cerca if lo[ea] <= pa <= hi[ea] and lo[eb] <= pb <= hi[eb]]
            if hit:
                tapados += 1
                ids.update(hit)
    return tapados / (n * n), sorted(ids)


def caras_cubiertas(doc, t) -> dict:
    """{techo, izquierda, derecha: {fraccion, piezas, cubierta}} del gabinete de `t`."""
    from .tablero import piezas_del_layout

    i = t.armado.interior
    W, D, H = i.ancho, i.fondo, i.alto
    cajas = _cajas_g(doc, t, piezas_del_layout(doc))
    x, y, z = (-W / 2, W / 2), (-D / 2, D / 2), (-H / 2, H / 2)
    out = {}
    for nombre, (eje, signo, borde, a, b, ejes) in {
            "techo": (2, +1, H / 2, x, y, (0, 1)),
            "izquierda": (0, -1, -W / 2, y, z, (1, 2)),
            "derecha": (0, +1, W / 2, y, z, (1, 2))}.items():
        fr, ids = _cubre(cajas, eje, signo, borde, a, b, ejes)
        out[nombre] = {"fraccion": round(fr, 2), "piezas": ids[:6], "cubierta": fr >= FRACCION_CUBIERTA}
    return out


# ── pérdidas y aparatos ───────────────────────────────────────────────────────────────────


def _tmax(comp) -> float | None:
    e = comp.electrico if comp is not None else None
    v = (e.datos or {}).get("T_max_C") if e is not None else None
    return float(v) if isinstance(v, (int, float)) else None


def perdidas(m, t) -> dict:
    """{aparatos_W, conductores_W, sin_dato, sin_corriente, conductores: n, ...} del tablero `t`."""
    from apolo.library.catalog import CATALOG
    from apolo.library.electrico.calentamiento import (
        Conductor,
        corriente_conductor,
        corriente_de_borne,
        perdidas_conductor,
    )

    u = t.ubicacion
    disp = {d.designacion: d for d in m.dispositivos}
    aparatos, sin_dato = 0.0, []
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
            aparatos += float(e.perdidas_W) * int(d.cantidad or 1)
    cables = {c.designacion: c for c in m.cables}
    conds = {c.id: c for c in m.conductores}
    total_c, sin_corr, sin_r, n = 0.0, [], [], 0
    for r in t.ruteo.rutas:
        c = conds.get(r.id)
        if c is None:
            continue
        seccion = c.seccion_mm2 or (cables[c.cable].seccion_mm2 if c.cable in cables else None)
        dichos = []
        for p in r.puntos:
            des, _, borne = p.rpartition(":")
            d = disp.get(des)
            b = d.borne(borne) if d is not None else None
            if b is not None:
                dichos.append(corriente_de_borne((d.modelo or {}).get("tipo"), d.modelo, d.ajustes, b.rol,
                                                 getattr(b, "lado", None)))
        corriente = corriente_conductor(dichos)
        w, motivo = perdidas_conductor(Conductor(r.id, seccion, r.largo_mm, corriente))
        total_c += w
        n += 1
        if motivo == "sin corriente asignada":
            sin_corr.append(r.id)
        elif motivo:
            sin_r.append(r.id)
    return {"aparatos_W": round(aparatos, 1), "conductores_W": round(total_c, 1),
            "total_W": round(aparatos + total_c, 1), "sin_dato": sin_dato, "sin_corriente": sin_corr,
            "sin_resistencia": sin_r, "n_conductores": n}


def aparatos_termicos(m, t, arm=None) -> list:
    """Un `AparatoTermico` por aparato del layout (altura de su borde superior) + los conductores."""
    from apolo.library.catalog import CATALOG
    from apolo.library.electrico.calentamiento import AparatoTermico

    arm = arm or t.armado
    H = arm.interior.alto
    tope: dict[str, float] = {}
    for pz in arm.piezas:
        if pz.designacion:
            tope[pz.designacion] = max(tope.get(pz.designacion, -1e9), pz.caja.z1)
    refs = {d.designacion: d.ref for d in m.dispositivos}
    out = []
    for des in sorted(tope):
        comp = CATALOG.get(refs.get(des, ""))
        h = min(max((tope[des] + H / 2) / H, 0.0), 1.0)
        out.append(AparatoTermico(des, h, _tmax(comp), comp.name if comp else des))
    ids = {r.id for r in t.ruteo.rutas}
    dentro = [c for c in m.conductores if c.id in ids]
    cables = {c.designacion: c.ref for c in m.cables}
    usados = {c.tipo for c in dentro if c.tipo} | {cables[c.cable] for c in dentro if c.cable in cables}
    tmax_c = [x for x in (_tmax(CATALOG.get(r)) for r in sorted(usados)) if x is not None]
    if tmax_c:
        out.append(AparatoTermico("conductores", 1.0, min(tmax_c), "Conductores (aislamiento)"))
    return out


# ── la evaluación ─────────────────────────────────────────────────────────────────────────


def _ambiente(doc, t) -> tuple[float, bool]:
    """(°C, ¿lo dio el comando?)."""
    cmd = next((c for c in doc.commands if c.get("id") == t.cid), {})
    dado = "ambiente_C" in (cmd.get("params") or {})
    return float(t.params.ambiente_C), dado


def _envolvente(interior, cub: dict):
    from apolo.library.electrico.iec60890 import Envolvente

    return Envolvente(interior.alto, interior.ancho, interior.fondo, techo_cubierto=cub["techo"]["cubierta"],
                      fondo_cubierto=True, laterales_cubiertos=sum(1 for k in ("izquierda", "derecha")
                                                                    if cub[k]["cubierta"]))


def _siguiente(doc, m, t, cub: dict, P: float, amb: float) -> dict | None:
    """El gabinete más chico, mayor que el de ahora, donde el layout entra y no se pasa."""
    from apolo.commands.errors import CommandError
    from apolo.library.catalog import CATALOG
    from apolo.library.electrico.calentamiento import evaluar
    from apolo.library.electrico.colocacion_catalogo import gabinetes_del_catalogo
    from apolo.library.electrico.iec60890 import FueraDeDominio

    from .tablero import plan_con_gabinete

    gabs = gabinetes_del_catalogo(CATALOG)
    actual = next((g for g in gabs if g.ref == t.layout.gabinete), None)
    for g in gabs:
        if actual is None or (g.area, g.ref) <= (actual.area, actual.ref):
            continue
        try:
            _lay, arm = plan_con_gabinete(doc, t.cid, g.ref)
            ev = evaluar(_envolvente(arm.interior, cub), P, aparatos_termicos(m, t, arm), amb)
        except (CommandError, ValueError, FueraDeDominio):
            continue
        if not ev.pasan:
            i = arm.interior
            return {"ref": g.ref, "nombre": CATALOG[g.ref].name, "medidas_mm": [i.ancho, i.fondo, i.alto],
                    "T_arriba_C": round(ev.T_arriba_C, 1), "Ae_m2": round(ev.calor.Ae_m2, 3)}
    return None


def evaluacion(doc, m, t) -> dict:
    """El calentamiento de UN tablero, listo para el panel y el ERC."""
    from apolo.library.electrico.calentamiento import FUENTE_R20, evaluar
    from apolo.library.electrico.iec60890 import FUENTE, METODO, FueraDeDominio

    cub = caras_cubiertas(doc, t)
    perd = perdidas(m, t)
    amb, dado = _ambiente(doc, t)
    env = _envolvente(t.armado.interior, cub)
    supuestos = [
        f"Método: {METODO}. Fuente: {FUENTE}.",
        f"Ambiente {amb:g} °C" + ("" if dado else " (no se dio: el de referencia del método)") + ".",
        "Gabinete de pared, sin aberturas: el fondo cuenta cubierto; el techo y cada lateral, si algo los "
        f"tapa en ≥ {FRACCION_CUBIERTA * 100:.0f} % a ≤ {HOLGURA_CUBIERTA_MM:g} mm (criterio de diseño).",
        "Pérdidas de cada aparato: las de su ficha a plena carga.",
        "Corriente de cada conductor: una cota superior por los bornes que une (el límite de la protección "
        "o de la fuente de la que sale, la suma de las protecciones que alimenta o la corriente asignada del "
        f"aparato); los de tierra, 0. R a 20 °C de {FUENTE_R20}.",
        "Temperatura de cada aparato: la del aire a la altura de su borde superior.",
    ]
    if perd["sin_dato"]:
        supuestos.append(f"Sin pérdidas en su ficha (cuentan 0 W): {', '.join(perd['sin_dato'])}.")
    if perd["sin_corriente"]:
        supuestos.append(f"{len(perd['sin_corriente'])} conductores de señal sin corriente asignada: 0 W.")
    base = {"metodo": METODO, "norma": NORMA, "ambiente_C": amb, "ambiente_dado": dado,
            **({"ventilacion_m3h": float(t.params.ventilacion_m3h)} if t.params.ventilacion_m3h else {}),
            "perdidas": perd, "caras": cub, "supuestos": supuestos}
    vent = float(t.params.ventilacion_m3h or 0.0)
    if vent > 0:
        supuestos.append(f"Ventilación forzada declarada de {vent:g} m³/h efectivos: balance de energía (IEC 60890 "
                         "es de convección natural); todo el aire del tablero a la temperatura con que sale.")
    try:
        ev = evaluar(env, perd["total_W"], aparatos_termicos(m, t), amb, vent)
    except FueraDeDominio as exc:
        return {**base, "estado": "sin_evaluar", "causa": "fuera_del_metodo", "motivo": str(exc)}
    c = ev.calor
    con = [x for x in ev.lecturas if x.T_max_C is not None]
    if not con:
        return {**base, "estado": "sin_evaluar", "causa": "sin_tmax",
                "motivo": "Ningún aparato del tablero trae su temperatura máxima en la ficha (T_max_C)."}
    out = {**base, "estado": "falla" if ev.pasan else "bien",
           "Ae_m2": round(c.Ae_m2, 3), "rama": c.rama, "tablas": list(c.tablas),
           "k": round(c.k, 4), "c": round(c.c, 4), "d": c.d, "x": c.x,
           **({"f": round(c.f, 3)} if c.f is not None else {}), **({"g": round(c.g, 3)} if c.g is not None else {}),
           **({"tipo_instalacion": c.tipo} if c.tipo is not None else {}),
           "dt_media_K": round(c.dt_media_K, 1), "dt_arriba_K": round(c.dt_arriba_K, 1),
           "T_media_C": round(ev.T_media_C, 1), "T_arriba_C": round(ev.T_arriba_C, 1),
           "aparatos": [{"designacion": x.designacion, "altura": x.h, "T_C": round(x.T_C, 1),
                         **({"T_max_C": x.T_max_C} if x.T_max_C is not None else {}),
                         **({"pasa": True} if x.pasa else {})} for x in ev.lecturas],
           "sin_tmax": list(ev.sin_tmax)}
    peor = ev.peor
    if peor is not None:
        out["peor"] = {"designacion": peor.designacion, "T_C": round(peor.T_C, 1), "T_max_C": peor.T_max_C}
    if ev.sin_tmax:
        out["supuestos"] = supuestos + [f"Sin temperatura máxima en su ficha (no se comparan): "
                                        f"{', '.join(ev.sin_tmax)}."]
    if ev.sugerencia is not None:
        s = ev.sugerencia
        out["sugerencia"] = {
            **({"caudal_m3h": s.caudal_m3h} if s.caudal_m3h is not None else {}),
            **({"entrada_cm2": s.entrada_cm2} if s.entrada_cm2 is not None else {}),
            **({"refrigeracion": True} if s.refrigeracion else {}),
            "dt_admisible_K": s.dt_admisible_K,
            **({"gabinete": g} if (g := _siguiente(doc, m, t, cub, perd["total_W"], amb)) else {})}
    return out


def evaluaciones(doc, m, tableros) -> dict[str, dict]:
    """{id del layout: evaluación} de cada tablero armado."""
    return {t.cid: evaluacion(doc, m, t) for t in tableros}


# ── el ERC ────────────────────────────────────────────────────────────────────────────────


def texto_sugerencia(s: dict) -> str:
    partes = []
    if s.get("refrigeracion"):
        return ("el ambiente ya pasa la máxima admisible: ventilar no alcanza, hace falta un equipo de "
                "refrigeración (fuera del método)")
    if s.get("caudal_m3h") is not None:
        partes.append(f"ventilación forzada de al menos {s['caudal_m3h']:.0f} m³/h efectivos (ventilador con "
                      "filtro abajo y rejilla con filtro arriba; el caudal de la ficha es a soplado libre, "
                      "mayor)")
    if s.get("entrada_cm2") is not None:
        partes.append(f"aberturas naturales de {s['entrada_cm2']:g} cm² de entrada abajo y ≥ "
                      f"{1.1 * s['entrada_cm2']:g} cm² de salida arriba")
    if s.get("gabinete"):
        g = s["gabinete"]
        partes.append(f"o el gabinete {g['ref']} ({g['T_arriba_C']:g} °C arriba, sin ventilar)")
    return "; ".join(partes)


def reglas(doc, m, tableros, evs: dict | None = None) -> list[dict]:
    """La fila «calentamiento del tablero» de cada tablero que se pasa o que no se pudo evaluar."""
    evs = evs if evs is not None else evaluaciones(doc, m, tableros)
    filas = []
    for t in tableros:
        e = evs.get(t.cid) or {}
        if e.get("estado") == "falla":
            malos = [a for a in e["aparatos"] if a.get("pasa")]
            lista = ", ".join(f"{a['designacion']} {a['T_C']:.0f} °C (máx. {a['T_max_C']:g})" for a in malos[:6])
            filas.append({
                "regla": "calentamiento del tablero", "estado": "error",
                "detalle": (f"{t.ubicacion} pierde {e['perdidas']['total_W']:g} W en Ae = {e['Ae_m2']:g} m²: el aire "
                            f"llega a {e['T_media_C']:.0f} °C a media altura y {e['T_arriba_C']:.0f} °C arriba "
                            f"(ambiente {e['ambiente_C']:g} °C) y pasa la máxima de {lista}. "
                            f"Sugerido: {texto_sugerencia(e.get('sugerencia') or {})}"),
                "recomendacion": (f"Ventila el tablero y declara el caudal efectivo del ventilador: "
                                  f"edit_command('{t.cid}', {{\"ventilacion_m3h\": "
                                  f"{math.ceil((e.get('sugerencia') or {}).get('caudal_m3h') or 0)}}}); o elige "
                                  "un gabinete mayor, o baja las pérdidas (un variador fuera del tablero)."),
                "norma": NORMA, "elementos": [f"{t.cid}_gabinete", *(a["designacion"] for a in malos[:6])]})
        elif e.get("estado") == "sin_evaluar":
            filas.append({"regla": "calentamiento del tablero", "estado": "aviso",
                          "detalle": f"{t.ubicacion}: no se pudo evaluar el calentamiento: {e.get('motivo')}",
                          "norma": NORMA, "elementos": [f"{t.cid}_gabinete"]})
    return filas
