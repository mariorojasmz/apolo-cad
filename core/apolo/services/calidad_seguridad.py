"""Seguridad para la puerta de publicación (plan puerta-de-publicacion, F3, D4): lee el documento,
extrae datos puros y corre los controles de `library/seguridad/`.

- `datos_calidad(doc)`: piezas (rol, catálogo, caja, redondez, anclaje), juntas, uniones
  declaradas, sólidos y la caja de la máquina — lo comparte la reparabilidad.
- `controles_seguridad(doc)`: los ítems `seguridad.resguardo_iso13857`,
  `seguridad.guarda_con_herramienta` y `seguridad.electrico`, más la tabla de riesgos.

Sin locks (el llamador sostiene `STATE_LOCK`); el trazado de rayos, en `calidad_sondas.py`.
"""

from __future__ import annotations

import time

ID_RESGUARDO = "seguridad.resguardo_iso13857"
ID_GUARDA = "seguridad.guarda_con_herramienta"
ID_ELECTRICO = "seguridad.electrico"
_TOCA_MM = 1.5           # una pieza redonda a ≤ 1,5 mm de la banda la toca
_NO_TAMBOR = {"estructura", "guarda", "flexible", "perno", "tuerca", "chumacera", "equipo",
              "pie", "eje"}


def _maquinas(doc) -> set[str]:
    """Nombres de máquina que encabezan los nombres de una plantilla («Faja de banda · …»): los
    grupos y el primer tramo común de los comandos que crean ≥ 3 piezas."""
    out = set(doc.groups) | {g.rsplit("/", 1)[-1] for g in doc.groups}
    por_cmd: dict[str, set[str]] = {}
    cuenta: dict[str, int] = {}
    for f in doc.scene.values():
        cmd = getattr(f, "command_id", None)
        tramos = [t.strip() for t in (f.name or "").split("·")]
        if cmd is None or len(tramos) < 2:
            continue
        por_cmd.setdefault(cmd, set()).add(tramos[0])
        cuenta[cmd] = cuenta.get(cmd, 0) + 1
    out |= {next(iter(s)) for c, s in por_cmd.items() if len(s) == 1 and cuenta[c] >= 3}
    return out


def _caja(shape):
    bb = shape.bounding_box()
    return ((bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z))


def datos_calidad(doc) -> dict:
    """{piezas: {id: Pieza}, juntas, uniones, solidos: {id: [Solid]}, caja, z_piso}."""
    from apolo.kernel.shapes import is_surface
    from apolo.library.catalog import CATALOG
    from apolo.library.seguridad.modelo import Pieza, redondo_de_caja

    from .roles import rol_union

    maquinas = _maquinas(doc)
    anclas = {g.get("feature") for g in doc.grounds.values()}
    piezas, solidos = {}, {}
    for fid, f in doc.scene.items():
        if getattr(f, "is_guide", False) or f.shape is None or is_surface(f.shape):
            continue
        try:
            sols = list(f.shape.solids())
        except Exception:  # noqa: BLE001
            continue
        if not sols:
            continue
        comp = CATALOG.get(getattr(f, "component", None) or "")
        cat = comp.category if comp else None
        rol, _ = rol_union(f.name, cat, comp.name if comp else None, maquinas)
        caja = _caja(f.shape)
        piezas[fid] = Pieza(fid, f.name or fid, rol, cat, comp.name if comp else None, caja,
                            redondo_de_caja(caja), fid in anclas)
        solidos[fid] = sols
    juntas = [dict(j) for j in doc.joints.values()]
    uniones = [{"a": u["a"], "b": u["b"], "kind": u.get("kind", "perno"),
                "name": u.get("name", "")} for u in doc.fasteners.values()
               if u.get("a") in piezas and u.get("b") in piezas]
    if piezas:
        lo = tuple(min(p.caja[0][i] for p in piezas.values()) for i in range(3))
        hi = tuple(max(p.caja[1][i] for p in piezas.values()) for i in range(3))
    else:
        lo = hi = (0.0, 0.0, 0.0)
    return {"piezas": piezas, "juntas": juntas, "uniones": uniones, "solidos": solidos,
            "caja": (lo, hi), "z_piso": lo[2]}


def _tocan(sa, sb) -> bool:
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    for a in sa:
        for b in sb:
            d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
            if d.IsDone() and d.Value() <= _TOCA_MM:
                return True
    return False


def tambores_de_banda(dc: dict) -> dict[str, list[str]]:
    """{banda: [piezas redondas que toca]}: unión declarada con la banda o a ≤ 1,5 mm de ella;
    sin rol que lo descarte y con el eje ⊥ al largo de la banda."""
    from apolo.library.seguridad.modelo import clase_flexible, es_tornilleria

    piezas, out = dc["piezas"], {}
    declaradas = {(u["a"], u["b"]) for u in dc["uniones"]}
    for b, pb in piezas.items():
        if clase_flexible(pb) != "banda":
            continue
        lo, hi = pb.caja
        largo = max(range(3), key=lambda i: hi[i] - lo[i])
        cands = []
        for i, p in piezas.items():
            if (i == b or p.redondo is None or p.rol in _NO_TAMBOR or es_tornilleria(p)
                    or p.redondo.eje == largo):
                continue
            if not all(p.caja[0][k] - 2 <= hi[k] and lo[k] - 2 <= p.caja[1][k] for k in range(3)):
                continue
            if (b, i) in declaradas or (i, b) in declaradas or \
                    _tocan(dc["solidos"][b], dc["solidos"][i]):
                cands.append(i)
        if cands:
            out[b] = cands
    return out


def _tambor_por_cuerpo(tocan: dict, piezas, gira, juntas, uniones) -> dict[str, list[str]]:
    """De cada cuerpo que gira, el redondo de MAYOR radio que toca la banda (el engomado, no
    el tubo que lleva adentro)."""
    from apolo.library.seguridad.peligros import cuerpos

    cuerpo_de = {i: frozenset(c) for c in cuerpos(gira, juntas, uniones) for i in c}
    out = {}
    for b, ids in tocan.items():
        mejor: dict = {}
        for i in ids:
            k = cuerpo_de.get(i, frozenset({i}))
            if k not in mejor or piezas[i].redondo.radio > piezas[mejor[k]].redondo.radio:
                mejor[k] = i
        out[b] = sorted(mejor.values())
    return out


def _item_electrico(doc) -> dict:
    from apolo.library.seguridad.modelo import item

    from .electrico import chequeo, tiene_carril

    titulo = "Peligro eléctrico: el tablero pasa el ERC"
    modo = "contacto directo o indirecto, protección mal dimensionada"
    norma = "IEC 60204-1 (equipo eléctrico de máquinas) vía ERC"
    if not tiene_carril(doc):
        return item(ID_ELECTRICO, titulo, "NO_APLICA", modo, norma,
                    {"motivo": "sin tablero eléctrico (carril vacío)"})
    erc = chequeo(doc)
    ev = {"estado_erc": erc.get("estado"), "errores": erc.get("errores", 0),
          "avisos": erc.get("avisos", 0)}
    estado = "FALLA" if erc.get("errores", 0) else "OK"
    return item(ID_ELECTRICO, titulo, estado, modo, norma, ev,
                detalle=f"ERC: {ev['errores']} errores, {ev['avisos']} avisos")


def controles_seguridad(doc, dc: dict | None = None, n_direcciones: int = 64) -> dict:
    """→ {items: [resguardo, guarda, eléctrico], riesgos: [filas], peligros: [...], ms}."""
    from apolo.library.seguridad import guardas as G
    from apolo.library.seguridad.iso13857 import NORMA as NORMA_13857
    from apolo.library.seguridad.modelo import clase_flexible, item
    from apolo.library.seguridad.peligros import (
        giratorias,
        peligros_mecanicos,
        resultado_peligro,
        tabla_riesgos,
    )

    from .calidad_sondas import Trazador, cunas, evaluar_peligro

    t0 = time.perf_counter()
    dc = dc or datos_calidad(doc)
    piezas, juntas, uniones = dc["piezas"], dc["juntas"], dc["uniones"]
    tocan = tambores_de_banda(dc)
    gira = giratorias(piezas, juntas, uniones, {i for ids in tocan.values() for i in ids})
    tambores = _tambor_por_cuerpo(tocan, piezas, gira, juntas, uniones)
    peligros = peligros_mecanicos(piezas, juntas, uniones, gira, tambores)
    tr = Trazador(dc["solidos"]) if peligros else None
    resultados = {}
    for p in peligros:
        if p.get("cuna"):
            b, t = p["cuna"]["banda"], p["cuna"]["tambor"]
            c = cunas(dc["solidos"][b], piezas[b].caja, piezas[t].caja, piezas[t].redondo)
            p["objetivos"] = c["puntos"]
            if not c["puntos"]:
                p["motivo"] = c.get("motivo")
        sondas, ms = evaluar_peligro(tr, p, dc["caja"], dc["z_piso"], n_direcciones)
        resultados[p["id"]] = resultado_peligro(p, sondas, ms)

    titulo = "Cada peligro mecánico queda fuera del alcance (sondas ISO 13857)"
    modo = "atrapamiento o enganche de manos y brazos en lo que gira o en una cuña"
    if not peligros:
        it_res = item(ID_RESGUARDO, titulo, "NO_APLICA", modo, NORMA_13857,
                      {"motivo": "ninguna pieza gira ni se mueve"})
    else:
        estados = [r["estado"] for r in resultados.values()]
        estado = ("FALLA" if "FALLA" in estados else
                  "SIN_EVALUAR" if "SIN_EVALUAR" in estados else "OK")
        malos = [p for p in peligros if resultados[p["id"]]["estado"] != "OK"]
        ev = {"peligros": [{**resultados[p["id"]], "peligro": p["peligro"], "tipo": p["tipo"]}
                           for p in peligros],
              "direcciones": n_direcciones, "rayos": tr.n_rayos,
              "excepcion": "el ramal de carga de la banda (zona de trabajo) no es peligro; "
                           "sus cuñas con los tambores sí"}
        it_res = item(ID_RESGUARDO, titulo, estado, modo, NORMA_13857, ev,
                      [i for p in malos for i in p["piezas"]],
                      "; ".join(f"{p['peligro']}: {resultados[p['id']]['estado']} "
                                f"({resultados[p['id']]['n_alcanzan']} sondas alcanzan)"
                                for p in malos[:6]) or f"{len(peligros)} peligros resguardados")

    moviles = gira | {i for i, p in piezas.items() if clase_flexible(p)}
    rg = G.revisar_guardas(piezas, uniones, moviles)
    tit_g = "La guarda fija se quita sólo con herramienta (atornillada, no soldada ni apoyada)"
    modo_g = "guarda que se quita a mano, que no se puede quitar, o que gira con la máquina"
    if not rg["guardas"]:
        it_g = item(ID_GUARDA, tit_g, "NO_APLICA", modo_g, G.NORMA,
                    {"motivo": "el modelo no tiene guardas", **rg})
    else:
        malas = [g for g in rg["guardas"] if g["estado"] != "OK"]
        it_g = item(ID_GUARDA, tit_g, "FALLA" if malas else "OK", modo_g, G.NORMA, rg,
                    [i for g in malas for i in g["ids"]],
                    "; ".join(f"{g['nombre']}: {g['motivo']}" for g in malas[:6])
                    or f"{len(rg['guardas'])} guardas atornilladas")

    it_e = _item_electrico(doc)
    riesgos = tabla_riesgos(peligros, resultados, piezas, ID_RESGUARDO)
    if it_e["estado"] != "NO_APLICA":
        riesgos.append({"peligro": "Contacto eléctrico directo o indirecto", "tipo": "eléctrico",
                        "piezas": [], "zona": None, "medida": "tablero verificado por el ERC",
                        "verificacion": ID_ELECTRICO, "estado": it_e["estado"]})
    return {"items": [it_res, it_g, it_e], "riesgos": riesgos, "peligros": peligros,
            "ms": round((time.perf_counter() - t0) * 1000.0)}


def controles_f3(doc, n_direcciones: int = 64) -> dict:
    """Los seis ítems de F3 (seguridad + reparabilidad) con UNA extracción, y la tabla de
    riesgos. → {items, riesgos, ms}."""
    from .calidad_reparabilidad import controles_reparabilidad

    t0 = time.perf_counter()
    dc = datos_calidad(doc)
    seg = controles_seguridad(doc, dc, n_direcciones)
    rep = controles_reparabilidad(doc, dc)
    return {"items": seg["items"] + rep["items"], "riesgos": seg["riesgos"],
            "ms": {"seguridad": seg["ms"], "reparabilidad": rep["ms"],
                   "total": round((time.perf_counter() - t0) * 1000.0)}}
