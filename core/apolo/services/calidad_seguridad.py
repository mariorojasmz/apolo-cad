"""Seguridad para la puerta de publicación (plan puerta-de-publicacion, F3, D4): lee el documento,
extrae datos puros y corre los controles de `library/seguridad/`.

- `datos_calidad(doc)`: piezas (rol, catálogo, caja, redondez, anclaje), juntas (las de giro sin
  accionar, marcadas `servicio`: `calidad_juntas.py`), uniones declaradas, sólidos, la caja de la
  máquina y el PISO (`z_piso`: el apoyo de lo anclado, no un perno de anclaje que entra en la
  losa) — lo comparte la reparabilidad.
- `analisis(doc, contexto)`: la DETECCIÓN (qué gira, los peligros, las guardas, las piezas de
  desgaste) sin sondas ni barridos. Con el `contexto` de una corrida de la puerta
  (`puerta_publicacion.Contexto`) se calcula UNA vez y la comparten los detectores
  (`puerta_hechos`) y los controles: el mismo criterio y una sola extracción OCCT;
- `controles_seguridad(doc)`: los ítems `seguridad.resguardo_iso13857`,
  `seguridad.guarda_con_herramienta` y `seguridad.electrico`, más la tabla de riesgos;
- `items_seguridad(doc, contexto)`: la `Fuente` «seguridad» del registro (F3 entero, una vez).

Sin locks (el llamador sostiene `STATE_LOCK`); el trazado de rayos, en `calidad_sondas.py`; las
sondas con el brazo doblado (sobre lo que las rectas dieron por resguardado), en `calidad_codo.py`.
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
    from .calidad_juntas import juntas_marcadas

    juntas, servicio = juntas_marcadas(doc)
    uniones = [{"a": u["a"], "b": u["b"], "kind": u.get("kind", "perno"),
                "name": u.get("name", "")} for u in doc.fasteners.values()
               if u.get("a") in piezas and u.get("b") in piezas]
    if piezas:
        lo = tuple(min(p.caja[0][i] for p in piezas.values()) for i in range(3))
        hi = tuple(max(p.caja[1][i] for p in piezas.values()) for i in range(3))
    else:
        lo = hi = (0.0, 0.0, 0.0)
    return {"piezas": piezas, "juntas": juntas, "uniones": uniones, "solidos": solidos,
            "caja": (lo, hi), "z_piso": z_piso(piezas, lo[2]),
            "servicio": servicio & set(piezas)}


def z_piso(piezas: dict, z_min: float) -> float:
    """El piso: el apoyo más bajo de lo ANCLADO (`ground`) que no es tornillería; sin anclajes, lo
    más bajo que no es tornillería. Un perno de anclaje entra en la losa: tomarlo por piso dejaba
    entrar las sondas por debajo de ella (F3b punto 5)."""
    from apolo.library.seguridad.modelo import es_tornilleria

    for cuales in (lambda p: p.anclada and not es_tornilleria(p), lambda p: not es_tornilleria(p)):
        zs = [p.caja[0][2] for p in piezas.values() if cuales(p)]
        if zs:
            return min(zs)
    return z_min


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


def _analizar(dc: dict) -> dict:
    from apolo.library.reparabilidad import piezas_de_desgaste
    from apolo.library.seguridad.guardas import revisar_guardas
    from apolo.library.seguridad.modelo import clase_flexible
    from apolo.library.seguridad.peligros import cuerpos, giro, peligros_mecanicos

    from .calidad_salidas import peligros_de_salida

    piezas, juntas, uniones = dc["piezas"], dc["juntas"], dc["uniones"]
    tocan = tambores_de_banda(dc)
    gira, acoples = giro(piezas, juntas, uniones, {i for ids in tocan.values() for i in ids})
    tambores = _tambor_por_cuerpo(tocan, piezas, gira, juntas, uniones)
    # lo que mueve la mano (una junta de servicio) se mueve: no es resguardo fijo ni ancla un cable
    moviles = gira | {i for i, p in piezas.items() if clase_flexible(p)} | dc.get("servicio", set())
    peligros = (peligros_mecanicos(piezas, juntas, uniones, gira, tambores, acoples)
                + peligros_de_salida(dc, cuerpos(gira, juntas, uniones)))
    return {"dc": dc, "tocan": tocan, "gira": gira, "tambores": tambores, "moviles": moviles,
            "acoples": sorted(acoples), "peligros": peligros,
            "guardas": revisar_guardas(piezas, uniones, moviles),
            "desgaste": piezas_de_desgaste(piezas)}


def analisis(doc, contexto=None) -> dict:
    """{dc, tocan, gira, tambores, moviles, peligros, guardas, desgaste}: lo que F3 detecta antes
    de medir. Con `contexto`, una vez por corrida (memo `f3.analisis`)."""
    if contexto is not None:
        return contexto.una_vez("f3.analisis", lambda: analisis(doc))
    return _analizar(datos_calidad(doc))


def _fila_electrica(estado: str | None) -> dict:
    fila = {"peligro": "Contacto eléctrico directo o indirecto", "tipo": "eléctrico",
            "piezas": [], "zona": None, "medida": "tablero verificado por el ERC",
            "verificacion": ID_ELECTRICO}
    return fila if estado is None else {**fila, "estado": estado}


def _alcanzan(r: dict) -> str:
    txt = f"{r['n_alcanzan']} sondas alcanzan"
    return txt + (f", {r['n_brazo_doblado']} con el brazo doblado" if r.get("n_brazo_doblado")
                  else "")


def _con_brazo_doblado(tr, dc: dict, peligros: list[dict], sondas: dict, resultados: dict,
                       n_direcciones: int, empuje) -> dict:
    """Las sondas con el brazo DOBLADO (`calidad_codo`) sobre los peligros que las rectas dieron
    por resguardados: el campo del brazo se arma UNA vez y sólo si hace falta. → evidencia."""
    from apolo.library.seguridad.peligros import resultado_peligro

    from .calidad_codo import campo_alcance, sondas_con_codo

    pendientes = [p for p in peligros if resultados[p["id"]]["estado"] == "OK"]
    if not pendientes:
        return {"peligros": 0, "motivo": "ningún peligro quedó resguardado por las rectas"}
    t0 = time.perf_counter()
    campo = campo_alcance(dc["solidos"], dc["caja"], dc["z_piso"], empuje)
    ms_campo = (time.perf_counter() - t0) * 1000.0
    for p in pendientes:
        extra, ms = sondas_con_codo(tr, campo, p, n_direcciones, empuje)
        resultados[p["id"]] = resultado_peligro(p, sondas[p["id"]] + extra,
                                                resultados[p["id"]]["ms"] + ms)
    return {"peligros": len(pendientes), "voxel_mm": round(campo.paso, 1),
            "ms_campo": round(ms_campo)}


def resguardos(rg: dict, resultados: dict, servicio: set, declarados: set) -> dict:
    """Las guardas que de verdad RESGUARDAN (F3b punto 2): las que pararon alguna sonda de un
    peligro detectado, o las declaradas en la función «resguardo» (`doc.funciones`). Una «tapa»
    que no cubre nada (la de una bornera dentro del tablero) no es resguardo: el rol «guarda» sale
    del nombre. Una SOLDADA es cerramiento permanente (ISO 14120 §3.2 lo admite) si a cada peligro
    que cubre también se llega por un resguardo MÓVIL —el cuerpo de una junta de servicio: la boca
    de inspección de la tapa soldada de un tanque—; detrás de otra guarda atornillada sigue siendo
    FALLA (la regla de la puerta para el mantenimiento: F0b, hallazgo 3, va en fase propia).
    → {**rg, guardas: [las que cuentan], no_resguardan: [{ids, nombre}]}."""
    bloq = {pid: set(r.get("bloqueado_por") or ()) for pid, r in resultados.items()}
    cubre = {}
    for g in rg["guardas"]:
        ids = set(g["ids"])
        cubre[g["nombre"], tuple(g["ids"])] = sorted(pid for pid, b in bloq.items() if b & ids)
    abren = set(servicio)
    cuentan, fuera = [], []
    for g in rg["guardas"]:
        suyos = cubre[g["nombre"], tuple(g["ids"])]
        if not suyos and not set(g["ids"]) & declarados:
            fuera.append({"ids": g["ids"], "nombre": g["nombre"]})
            continue
        g = {**g, "cubre": suyos}
        if g["soldadas"] and not g["moviles"] and suyos and all(
                (bloq[pid] - set(g["ids"])) & abren for pid in suyos):
            g.update(estado="OK", motivo="cerramiento permanente (soldado, ISO 14120 §3.2): a lo "
                     "que cubre se llega por un resguardo móvil")
        cuentan.append(g)
    return {**rg, "guardas": cuentan, "no_resguardan": fuera}


def controles_seguridad(doc, dc: dict | None = None, n_direcciones: int = 64, *,
                        an: dict | None = None, electrico: bool = True,
                        brazo_doblado: bool = True, banda_empujable: bool = True) -> dict:
    """→ {items: [resguardo, guarda, eléctrico], riesgos: [filas], peligros: [...], ms}. `an`: el
    `analisis` ya hecho; `electrico=False` no corre el ERC (ni su ítem ni su fila);
    `brazo_doblado=False` deja sólo las sondas rectas y `banda_empujable=False` hace de la banda una
    pared también en las aberturas (las dos, para medir el hueco que cierran: F6)."""
    from apolo.library.seguridad import guardas as G
    from apolo.library.seguridad.iso13857 import NORMA as NORMA_13857
    from apolo.library.seguridad.modelo import item
    from apolo.library.seguridad.peligros import resultado_peligro, tabla_riesgos

    from .calidad_codo import BandaEmpujable
    from .calidad_cunas import DESCONOCIDO, llegadas
    from .calidad_sondas import Trazador, cunas, evaluar_peligro

    t0 = time.perf_counter()
    an = an or _analizar(dc or datos_calidad(doc))
    dc, piezas = an["dc"], an["dc"]["piezas"]
    peligros = [dict(p) for p in an["peligros"]]  # se les ponen objetivos: el análisis no cambia
    tr = Trazador(dc["solidos"]) if peligros else None
    empuje = BandaEmpujable(dc) if peligros and banda_empujable else None  # se empuja (F6)
    resultados, sondas_de = {}, {}
    entradas = llegadas(doc, {**an, "peligros": peligros}) if peligros else {}
    for p in peligros:
        if p.get("cuna"):
            b, t = p["cuna"]["banda"], p["cuna"]["tambor"]
            ent = entradas.get(p["id"]) or {"hacia": None, "sentido": DESCONOCIDO}
            c = cunas(dc["solidos"][b], piezas[b].caja, piezas[t].caja, piezas[t].redondo,
                      ent["hacia"])
            p["objetivos"] = c["puntos"]
            p["sentido"] = ent["sentido"]
            if ent["hacia"] is not None and c.get("cuna") == "entrada":
                p["peligro"] += " (cuña de entrada)"
            elif ent["hacia"] is not None and c["puntos"]:
                p["sentido"] = (f"las dos cuñas: ningún borde del arco queda claro como el de "
                                f"entrada ({ent['sentido'].split('; ', 1)[-1]})")
            if not c["puntos"]:
                p["motivo"] = c.get("motivo")
        sondas, ms = evaluar_peligro(tr, p, dc["caja"], dc["z_piso"], n_direcciones,
                                     empuje.salta if empuje is not None else None)
        sondas_de[p["id"]] = sondas
        resultados[p["id"]] = resultado_peligro(p, sondas, ms)
    doblado = (_con_brazo_doblado(tr, dc, peligros, sondas_de, resultados, n_direcciones, empuje)
               if brazo_doblado and peligros else None)

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
                           "sus cuñas con los tambores sí",
              **({"brazo_doblado": doblado} if doblado is not None else {})}
        it_res = item(ID_RESGUARDO, titulo, estado, modo, NORMA_13857, ev,
                      [i for p in malos for i in p["piezas"]],
                      "; ".join(f"{p['peligro']}: {resultados[p['id']]['estado']} "
                                f"({_alcanzan(resultados[p['id']])})"
                                for p in malos[:6]) or f"{len(peligros)} peligros resguardados")

    declarados = {i for f in (getattr(doc, "funciones", None) or [])
                  if f.get("funcion") == "resguardo" for i in f.get("piezas") or ()}
    rg = resguardos(an["guardas"], resultados, dc.get("servicio", set()), declarados)
    tit_g = "La guarda fija se quita sólo con herramienta (atornillada, no soldada ni apoyada)"
    modo_g = "guarda que se quita a mano, que no se puede quitar, o que gira con la máquina"
    if not rg["guardas"]:
        it_g = item(ID_GUARDA, tit_g, "NO_APLICA", modo_g, G.NORMA,
                    {"motivo": ("ninguna guarda cubre un peligro detectado ni está declarada como "
                                "resguardo") if rg["no_resguardan"] else "el modelo no tiene guardas",
                     **rg})
    else:
        malas = [g for g in rg["guardas"] if g["estado"] != "OK"]
        it_g = item(ID_GUARDA, tit_g, "FALLA" if malas else "OK", modo_g, G.NORMA, rg,
                    [i for g in malas for i in g["ids"]],
                    "; ".join(f"{g['nombre']}: {g['motivo']}" for g in malas[:6])
                    or f"{len(rg['guardas'])} guardas atornilladas")

    items = [it_res, it_g]
    riesgos = tabla_riesgos(peligros, resultados, piezas, ID_RESGUARDO)
    if electrico:
        it_e = _item_electrico(doc)
        items.append(it_e)
        if it_e["estado"] != "NO_APLICA":
            riesgos.append(_fila_electrica(it_e["estado"]))
    return {"items": items, "riesgos": riesgos, "peligros": peligros, "resultados": resultados,
            "ms": round((time.perf_counter() - t0) * 1000.0)}


def controles_f3(doc, n_direcciones: int = 64, *, contexto=None, electrico: bool = True) -> dict:
    """Los seis ítems de F3 (seguridad + reparabilidad) con UNA extracción, y la tabla de
    riesgos. → {items, riesgos, ms}. `contexto`: el de la corrida de la puerta (el `analisis`
    que ya usaron los detectores)."""
    from .calidad_reparabilidad import controles_reparabilidad

    t0 = time.perf_counter()
    an = analisis(doc, contexto)
    seg = controles_seguridad(doc, an["dc"], n_direcciones, an=an, electrico=electrico)
    if contexto is not None:  # los peligros medidos (objetivos y resguardos) para la prueba de
        # sobrantes (`calidad_sobrantes`), que re-traza sólo los que una pieza toca
        contexto.una_vez("f3.sondas", lambda: {k: seg[k] for k in ("peligros", "resultados")})
    rep = controles_reparabilidad(doc, an["dc"], an=an)
    return {"items": seg["items"] + rep["items"], "riesgos": seg["riesgos"],
            "ms": {"seguridad": seg["ms"], "reparabilidad": rep["ms"],
                   "total": round((time.perf_counter() - t0) * 1000.0)}}


def items_seguridad(doc, contexto=None) -> dict:
    """La `Fuente` «seguridad» del registro (`library/calidad/registro.py`): F3 entero en UNA
    corrida (las sondas cuestan hasta ~34 s) → {items, riesgos, ms}. El registro lleva los ítems a
    sus generales y publica `riesgos` (la tabla ISO 12100) en el resultado de la puerta.

    `seguridad.electrico` se DESCARTA a propósito: repite la `Entrada` `riesgos.electrico` (el
    mismo ERC, y ésa además bloquea los avisos); publicar los dos daría dos ítems para un mismo
    modo de falla y, si discreparan, dos veredictos. Por eso aquí el ERC no corre. Su fila de la
    tabla de riesgos se queda, SIN estado propio y verificada por `riesgos.electrico`: el registro
    le pone el estado de ese ítem."""
    from .electrico import tiene_carril

    r = controles_f3(doc, contexto=contexto, electrico=False)
    riesgos = list(r["riesgos"])
    if tiene_carril(doc):
        riesgos.append({**_fila_electrica(None), "verificacion": "riesgos.electrico"})
    items = [i for i in r["items"] if i["id"] != ID_ELECTRICO]  # descartado: ver el docstring
    return {"items": items, "riesgos": riesgos, "ms": r["ms"]}
