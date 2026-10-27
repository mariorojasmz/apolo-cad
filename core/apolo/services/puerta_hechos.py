"""Los DETECTORES de la puerta de publicación (plan puerta-de-publicacion, D14): qué ELEMENTOS
tiene el modelo, por tipo general y clase concreta, para que cada ítem general del registro
(`library/calidad/registro.py`) sepa si aplica y diga qué evaluó. El llamador sostiene STATE_LOCK.

`hechos(doc, entrega_kwargs, contexto)` →
- `elementos`: {tipo general: {clase: n}} — `transmisiones_flexibles` {banda, cadena},
  `elementos_rodantes` {rodamiento, chumacera}, `accionamientos`, `transmisiones`, `apoyos`,
  `vigas`, `columnas`, `uniones` / `uniones_apernadas` / `soldaduras`, `tornilleria`,
  `tornilleria_llave`, `supercomandos`, `piezas` {catalogo, a_medida}, `sustitutos_animados`
  {banda}, `partes_moviles`, `resguardos`, `consumibles`, `operables` (mandos, pilotos y sensores
  que piden su nombre por función, por tipo). **Una familia de máquinas nueva suma
  aquí su clase** (p. ej. `transmisiones_flexibles["correa"]`), nunca un ítem al registro;
- `familias_funcion`: {familia D15: [piezas]} (sólo las que el modelo tiene);
- banderas: `pocos_solidos`, `sin_estudios`, `sin_poses`, `carril`, `escenarios`,
  `memoria_aplica`, `mueve_producto` (productos en los escenarios o bandas con tablero:
  `flujo_producto.mueve_producto`, plan balance-de-producto D9).

Cada detector usa el MISMO criterio que el control que lo evalúa (la tornillería:
`calidad_pernos.tipo_de_tornilleria`; los lazos: `calidad_tensores`; la banda animada:
`marcha_ejemplo.bandas`; `partes_moviles`, `resguardos`, `consumibles` y la familia `resguardo`:
la detección de F3, `calidad_seguridad.analisis` — los peligros de `peligros_mecanicos` por clase,
las guardas de `guardas.revisar_guardas` y las piezas de `reparabilidad.piezas_de_desgaste`—,
compartida con la fuente «seguridad» por el `contexto` de la corrida). Si esa detección revienta,
los tres tipos quedan con `sin_detectar` (aplican: la fuente dirá por qué no corrió), nunca vacíos.
"""

from __future__ import annotations

_MOTORES = ("motorreductores", "motorreductores_sinfin")
_RODANTES = {"rodamientos": "rodamiento", "chumaceras": "chumacera"}
_GIRO = ("giratoria", "continua")
#: clase de cada peligro de `peligros_mecanicos` (por el prefijo de su id)
_CLASE_PELIGRO = {"atrapamiento": "cuna_banda_tambor", "transmision": "transmision",
                  "extremo_eje": "extremo_eje", "giro": "pieza_giratoria",
                  "salida_motor": "salida_motorreductor"}


def _n(d: dict) -> dict:
    return {k: v for k, v in d.items() if v}


def _vigas(doc) -> dict:
    """{perfil: n, bastidor_faja: n}: lo que `vigas_rules` calcula como viga (perfil horizontal
    con dos apoyos por perno o soldadura) y las piezas de un `create_conveyor`, que calcula su
    regla («flecha del bastidor»). El MISMO criterio que el control (F3c de
    puerta-sin-sobrediseno): un perfil cualquiera —un riel DIN, una canaleta, las patas de un
    tanque a compresión— no es una viga y el ítem sale NO_APLICA, no SIN_EVALUAR."""
    from .vigas_rules import detectar_vigas

    try:
        det = detectar_vigas(doc)
    except Exception:  # noqa: BLE001 — aplica igual: la fuente dirá por qué no se evaluó
        return {"sin_detectar": 1}
    if det is None:
        return {}
    return {"perfil": len(det["vigas"]), "bastidor_faja": len(det["de_faja"])}


def _columnas(doc) -> dict:
    """{pata, columna, sin_evaluar}: lo que miden las reglas de pandeo —las patas de
    `report_estructura` y las columnas de `columnas_rules` (evaluables o no evaluadas, que se
    justifican)—, con el MISMO criterio que el control (F3f de puerta-sin-sobrediseno: antes
    contaba roles «columna»/«poste» que ninguna regla evaluaba, SIN_EVALUAR sin salida)."""
    from .columnas_rules import detectar_columnas

    try:
        c = detectar_columnas(doc)
    except Exception:  # noqa: BLE001 — aplica igual: la fuente dirá por qué no se evaluó
        return {"sin_detectar": 1}
    return _n({"pata": c["patas"], "columna": len(c["evaluables"]),
               "sin_evaluar": len(c["no_evaluadas"])})


def _ground_fid(g) -> str | None:
    return g.get("feature") or g.get("a") if isinstance(g, dict) else None


def _de_f3(doc, contexto) -> tuple[dict, dict, dict, list[str]]:
    """(partes_moviles, resguardos, consumibles, ids de las guardas) con el criterio de F3."""
    from .calidad_seguridad import analisis

    try:
        an = analisis(doc, contexto)
    except Exception:  # noqa: BLE001 — aplican igual: la fuente «seguridad» dirá el error
        return {"sin_detectar": 1}, {"sin_detectar": 1}, {"sin_detectar": 1}, []
    moviles: dict[str, int] = {}
    for p in an["peligros"]:
        clase = _CLASE_PELIGRO.get(p["id"].split(":", 1)[0], "otro")
        moviles[clase] = moviles.get(clase, 0) + 1
    consumibles: dict[str, int] = {}
    for clase in an["desgaste"].values():
        consumibles[clase] = consumibles.get(clase, 0) + 1
    guardas = an["guardas"]["guardas"]
    return (moviles, _n({"guarda": len(guardas)}), consumibles,
            [i for g in guardas for i in g["ids"]])


def hechos(doc, entrega_kwargs: dict, contexto=None) -> dict:
    from apolo.commands.exec_rodillos_cadena import comandos_efectivos
    from apolo.library.calidad.nombres import elementos as elementos_operables
    from apolo.library.catalog import CATALOG
    from apolo.library.delivery import MIN_SOLIDOS_SUJECION

    from . import marcha_ejemplo
    from .calidad_juntas import clasificar
    from .calidad_pernos import tipo_de_tornilleria
    from .calidad_tensores import lazos_banda
    from .electrico import tiene_carril
    from .flujo_producto import mueve_producto

    solidos = {f: x for f, x in doc.scene.items() if not getattr(x, "is_guide", False)}
    comps = {f: CATALOG.get(getattr(x, "component", None) or "") for f, x in solidos.items()}
    cadenas = [c["id"] for c in comandos_efectivos(doc.commands, doc.variables_resolved)
               if c["type"] == "create_chain"]
    bandas = [lz["id"] for lz in lazos_banda(doc)]
    por_cmd: dict[str, int] = {}
    for x in solidos.values():
        por_cmd[x.command_id] = por_cmd.get(x.command_id, 0) + 1
    kinds = [f.get("kind", "perno") for f in doc.fasteners.values()]
    try:
        animadas = len(marcha_ejemplo.bandas(doc)[0])
    except Exception:  # noqa: BLE001 — sin la detección, se evalúa igual y dirá por qué
        animadas = len(bandas)
    tornilleria: dict[str, int] = {}
    for x in solidos.values():
        t = tipo_de_tornilleria(x, CATALOG)
        if t:
            tornilleria[t] = tornilleria.get(t, 0) + 1
    rodantes = {f: _RODANTES[c.category] for f, c in comps.items()
                if c is not None and c.category in _RODANTES}
    motores = [f for f, c in comps.items() if c is not None and c.category in _MOTORES]
    # lo que gira accionado (una bisagra de servicio no es apoyo rotativo: `calidad_juntas`)
    accionadas = {n for n, c in clasificar(doc).items() if c["accionada"]}
    giran = [j["child"] for n, j in doc.joints.items() if j.get("type") in _GIRO and n in accionadas]
    vigas = _vigas(doc)
    partes_moviles, resguardos, consumibles, guardas = _de_f3(doc, contexto)
    anclados = [g for g in (_ground_fid(x) for x in doc.grounds.values()) if g in solidos]
    # un MECANISMO (memoria y familias D15): lo que se mueve por el modelo o un peligro de F3
    mecanismo = bool(doc.joints or bandas or cadenas or motores or rodantes or partes_moviles)
    familias = {k: v for k, v in {
        "transmision_flexible": bandas + cadenas,
        "apoyo_rotativo": list(rodantes) + giran,
        "accionamiento": motores,
        "resguardo": guardas if mecanismo else [],
        "estructura": (anclados or list(solidos)) if mecanismo else [],
    }.items() if v}
    elementos = {
        "transmisiones_flexibles": _n({"banda": len(bandas), "cadena": len(cadenas)}),
        "elementos_rodantes": _n({c: sum(1 for v in rodantes.values() if v == c)
                                  for c in _RODANTES.values()}),
        "accionamientos": _n({"motorreductor": len(motores)}),
        "transmisiones": _n({"cadena": len(cadenas)}),
        "apoyos": _n({"anclaje": len(doc.grounds)}),
        "vigas": _n(vigas),
        "columnas": _columnas(doc),
        "uniones": _n({"perno": kinds.count("perno"), "soldadura": kinds.count("soldadura")}),
        "uniones_apernadas": _n({"perno": kinds.count("perno")}),
        "soldaduras": _n({"soldadura": kinds.count("soldadura")}),
        "tornilleria": _n(tornilleria),
        "tornilleria_llave": _n({"fijador": int("acceso_herramienta" in entrega_kwargs)}),
        "supercomandos": _n({"super-comando": sum(1 for n in por_cmd.values() if n >= 2)}),
        "piezas": _n({"catalogo": sum(1 for c in comps.values() if c is not None),
                      "a_medida": sum(1 for c in comps.values() if c is None)}),
        "sustitutos_animados": _n({"banda": animadas}),
        "partes_moviles": partes_moviles,
        "resguardos": resguardos,
        "consumibles": consumibles,
        # nombres-por-funcion D4: los mandos, pilotos y sensores que el ítem juzga, por tipo, con
        # el criterio de su control (`calidad/nombres.en_alcance`) sobre el insumo de la entrega
        "operables": elementos_operables(entrega_kwargs.get("nombres")),
    }
    return {
        "n_solidos": len(solidos),
        "pocos_solidos": len(solidos) < MIN_SOLIDOS_SUJECION,
        "sin_estudios": not doc.motion,
        "sin_poses": entrega_kwargs.get("poses") == [],
        "carril": tiene_carril(doc),
        "escenarios": bool(doc.escenarios),
        "mueve_producto": mueve_producto(doc, len(bandas)),
        "memoria_aplica": bool(mecanismo or elementos["uniones"] or doc.requirements
                               or doc.grounds),
        "elementos": elementos,
        "familias_funcion": familias,
    }


def fabricacion(doc) -> dict:
    """{piezas, catalogo, procesos {clave: n}, malas [{id, nombre, motivo}]}: cada pieza es de
    catálogo o un sólido real (válido, con volumen) con material y proceso resueltos."""
    from apolo.drawing.process import infer_process
    from apolo.library.catalog import CATALOG
    from apolo.library.materials import resolve_material

    out = {"piezas": 0, "catalogo": 0, "procesos": {}, "malas": []}
    for fid, f in doc.scene.items():
        if getattr(f, "is_guide", False):
            continue
        out["piezas"] += 1
        comp = CATALOG.get(getattr(f, "component", None) or "")
        if comp is not None:
            out["catalogo"] += 1
            continue
        motivo = None
        try:
            valido = getattr(f.shape, "is_valid", False)  # build123d: propiedad (antes, método)
            valido = valido() if callable(valido) else valido
            if f.shape is None or not valido or float(f.shape.volume) <= 1e-6:
                motivo = "no es un sólido cerrado con volumen"
        except Exception:  # noqa: BLE001 — una forma que no se mide no se fabrica
            motivo = "su geometría no se puede medir"
        material = None if motivo else resolve_material(f, CATALOG)
        if motivo is None and not material:
            motivo = "sin material"
        if motivo:
            out["malas"].append({"id": fid, "nombre": f.name, "motivo": motivo})
            continue
        clave = infer_process(f)["key"]
        out["procesos"][clave] = out["procesos"].get(clave, 0) + 1
    return out
