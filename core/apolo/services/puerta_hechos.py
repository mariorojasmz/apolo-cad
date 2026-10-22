"""Los DETECTORES de la puerta de publicación (plan puerta-de-publicacion, D14): qué ELEMENTOS
tiene el modelo, por tipo general y clase concreta, para que cada ítem general del registro
(`library/calidad/registro.py`) sepa si aplica y diga qué evaluó. El llamador sostiene STATE_LOCK.

`hechos(doc, entrega_kwargs)` →
- `elementos`: {tipo general: {clase: n}} — `transmisiones_flexibles` {banda, cadena},
  `elementos_rodantes` {rodamiento, chumacera}, `accionamientos`, `transmisiones`, `apoyos`,
  `vigas`, `columnas`, `uniones` / `uniones_apernadas` / `soldaduras`, `tornilleria`,
  `tornilleria_llave`, `supercomandos`, `piezas` {catalogo, a_medida}, `sustitutos_animados`
  {banda}, `partes_moviles`, `resguardos`, `consumibles`. **Una familia de máquinas nueva suma
  aquí su clase** (p. ej. `transmisiones_flexibles["correa"]`), nunca un ítem al registro;
- `familias_funcion`: {familia D15: [piezas]} (sólo las que el modelo tiene);
- banderas: `pocos_solidos`, `sin_estudios`, `sin_poses`, `carril`, `escenarios`,
  `memoria_aplica`.

Cada detector usa el MISMO criterio que el control que lo evalúa (la tornillería:
`calidad_pernos.tipo_de_tornilleria`; los lazos: `calidad_tensores`; la banda animada:
`marcha_ejemplo.bandas`).
"""

from __future__ import annotations

import re

_PATA_RE = re.compile(r"^(patas?|columnas?|postes?)\b", re.I)
_GUARDA_RE = re.compile(r"^(guardas?|resguardos?|cárter|carter)\b", re.I)
_MOTORES = ("motorreductores", "motorreductores_sinfin")
_RODANTES = {"rodamientos": "rodamiento", "chumaceras": "chumacera"}
_GIRO = ("giratoria", "continua")
_VIGA_MIN_MM = 300.0  # un perfil horizontal más corto no trabaja como viga


def _n(d: dict) -> dict:
    return {k: v for k, v in d.items() if v}


def _horizontal_largo(shape) -> bool:
    bb = shape.bounding_box()
    dx, dy, dz = bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z
    return max(dx, dy) >= max(dz, _VIGA_MIN_MM)


def _ground_fid(g) -> str | None:
    return g.get("feature") or g.get("a") if isinstance(g, dict) else None


def hechos(doc, entrega_kwargs: dict) -> dict:
    from apolo.commands.exec_rodillos_cadena import comandos_efectivos
    from apolo.library.catalog import CATALOG
    from apolo.library.delivery import MIN_SOLIDOS_SUJECION
    from apolo.library.materials import piece_role

    from . import marcha_ejemplo
    from .calidad_pernos import tipo_de_tornilleria
    from .calidad_tensores import lazos_banda
    from .electrico import tiene_carril

    solidos = {f: x for f, x in doc.scene.items() if not getattr(x, "is_guide", False)}
    comps = {f: CATALOG.get(getattr(x, "component", None) or "") for f, x in solidos.items()}
    rol = {f: piece_role(x.name or "") for f, x in solidos.items()}
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
    tornilleria = {"perno": 0, "madera": 0}
    for x in solidos.values():
        t = tipo_de_tornilleria(x, CATALOG)
        if t:
            tornilleria[t] += 1
    rodantes = {f: _RODANTES[c.category] for f, c in comps.items()
                if c is not None and c.category in _RODANTES}
    motores = [f for f, c in comps.items() if c is not None and c.category in _MOTORES]
    giran = [j["child"] for j in doc.joints.values() if j.get("type") in _GIRO]
    vigas = 0
    for f, c in comps.items():
        if c is not None and c.cuttable:
            try:
                vigas += _horizontal_largo(solidos[f].shape)
            except Exception:  # noqa: BLE001 — sin bbox no cuenta
                pass
    guardas = [f for f, r in rol.items() if _GUARDA_RE.match(r)]
    anclados = [g for g in (_ground_fid(x) for x in doc.grounds.values()) if g in solidos]
    moviles = _n({"junta": len(doc.joints), "transmision_flexible": len(bandas) + len(cadenas),
                  "accionamiento": len(motores), "elemento_rodante": len(rodantes)})
    familias = {k: v for k, v in {
        "transmision_flexible": bandas + cadenas,
        "apoyo_rotativo": list(rodantes) + giran,
        "accionamiento": motores,
        "resguardo": guardas if moviles else [],
        "estructura": (anclados or list(solidos)) if moviles else [],
    }.items() if v}
    elementos = {
        "transmisiones_flexibles": _n({"banda": len(bandas), "cadena": len(cadenas)}),
        "elementos_rodantes": _n({c: sum(1 for v in rodantes.values() if v == c)
                                  for c in _RODANTES.values()}),
        "accionamientos": _n({"motorreductor": len(motores)}),
        "transmisiones": _n({"cadena": len(cadenas)}),
        "apoyos": _n({"anclaje": len(doc.grounds)}),
        "vigas": _n({"perfil": vigas}),
        "columnas": _n({"pata": sum(1 for r in rol.values() if _PATA_RE.match(r))}),
        "uniones": _n({"perno": kinds.count("perno"), "soldadura": kinds.count("soldadura")}),
        "uniones_apernadas": _n({"perno": kinds.count("perno")}),
        "soldaduras": _n({"soldadura": kinds.count("soldadura")}),
        "tornilleria": _n(tornilleria),
        "tornilleria_llave": _n({"fijador": int("acceso_herramienta" in entrega_kwargs)}),
        "supercomandos": _n({"super-comando": sum(1 for n in por_cmd.values() if n >= 2)}),
        "piezas": _n({"catalogo": sum(1 for c in comps.values() if c is not None),
                      "a_medida": sum(1 for c in comps.values() if c is None)}),
        "sustitutos_animados": _n({"banda": animadas}),
        "partes_moviles": moviles,
        "resguardos": _n({"guarda": len(guardas)}),
        "consumibles": _n({"banda": len(bandas), "cadena": len(cadenas),
                           "rodamiento": len(rodantes)}),
    }
    return {
        "n_solidos": len(solidos),
        "pocos_solidos": len(solidos) < MIN_SOLIDOS_SUJECION,
        "sin_estudios": not doc.motion,
        "sin_poses": entrega_kwargs.get("poses") == [],
        "carril": tiene_carril(doc),
        "escenarios": bool(doc.escenarios),
        "memoria_aplica": bool(moviles or elementos["uniones"] or doc.requirements
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
