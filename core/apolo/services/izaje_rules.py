"""Regla «capacidad de la cadena de izaje» de un documento (plan `docs/plans/cadena-de-izaje.md`,
F2a): mide lo que cuelga de cada cadena de `create_hoist_chain` y deja el cálculo a
`library/engineering/izaje_capacidad.py` (puro). La llama `structure_rules`: la comparten
`/api/checks`, la memoria de cálculo y la puerta de publicación. El llamador sostiene STATE_LOCK.

Una cadena de izaje se reconoce por su pieza (`mesh_key` «izaje|…», la clave de
`izaje_geom.clave`) y sus amarres por las uniones que DECLARÓ su comando: `{id}_pasador_a|b`
(cadena ↔ ancla) y `{id}_amarre_a|b` (ancla ↔ pieza), con el `command_id` de la cadena. Así
también la encuentra en un `insert_project`, sin depender del tipo del comando en el log.

El cuerpo que cuelga de un extremo es el CUERPO MÓVIL de su pieza de amarre: se sube por las
juntas `fija` hasta la primera junta que mueve (prismática o de giro) y se suma su hijo con todo
lo que cuelga de él por juntas (lo que la FK mueve junto). Si la pieza no cuelga de ninguna
junta que mueve, se usa el grafo de conectividad sin las cadenas de izaje: lo que queda unido a
la pieza tiene que quedar sin tierra (si toca tierra por otro lado, el reparto no es
determinable y la regla lo dice, sin inventar una cifra).

Devuelve también los nombres de los pasadores que la regla VERIFICÓ: `report_uniones` deja de
contarlos «sin dimensionar» (el pasador es el perno de la cadena, ISO 606: su capacidad es la
rotura de la cadena). Un pasador de una cadena cuya carga no se pudo determinar sigue sin
dimensionar: nada queda sin verificar en silencio.
"""

from __future__ import annotations

PREFIJO = "izaje|"


def _cadenas_de_izaje(doc) -> list[tuple[str, object, dict]]:
    """[(fid, feature, {lado: (pasador, amarre, pieza)})] de cada cadena de izaje de la escena
    con sus dos amarres declarados por su propio comando."""
    out = []
    for fid, f in doc.scene.items():
        if not str(getattr(f, "mesh_key", None) or "").startswith(PREFIJO):
            continue
        cmd = getattr(f, "command_id", None)
        lados = {}
        for lado in "ab":
            pas = doc.fasteners.get(f"{fid}_pasador_{lado}")
            ama = doc.fasteners.get(f"{fid}_amarre_{lado}")
            if (pas is None or ama is None or pas.get("command_id") != cmd
                    or ama.get("command_id") != cmd or pas.get("a") != fid
                    or ama.get("a") != pas.get("b") or ama.get("b") not in doc.scene):
                continue
            lados[lado] = (pas["name"], ama["name"], ama["b"])
        out.append((fid, f, lados))
    return out


def _cuerpo_movil(joints: dict, fid: str) -> tuple[str, set[str]] | None:
    """(conductor, piezas) del cuerpo que mueve la primera junta NO fija por encima de `fid`; None
    si no cuelga de ninguna."""
    por_hijo = {j["child"]: j for j in joints.values()}
    actual, vistos = fid, set()
    while actual in por_hijo and actual not in vistos:
        vistos.add(actual)
        j = por_hijo[actual]
        if j["type"] != "fija":
            break
        actual = j["parent"]
    else:
        return None
    hijos: dict[str, list[str]] = {}
    for j in joints.values():
        hijos.setdefault(j["parent"], []).append(j["child"])
    cuerpo, pila = set(), [actual]
    while pila:
        n = pila.pop()
        if n in cuerpo:
            continue
        cuerpo.add(n)
        pila.extend(hijos.get(n, ()))
    return actual, cuerpo


def _colgado_por_grafo(doc, fid: str, cadenas: set[str]) -> set[str] | None:
    """Lo unido a `fid` sin pasar por las cadenas de izaje; None si eso toca tierra (la cadena no
    es su único sostén: reparto indeterminado)."""
    from apolo.assembly.connectivity import build_graph

    g = build_graph(doc.scene, doc.joints, doc.mates, doc.fasteners, doc.grounds)
    comp, pila = set(), [fid]
    while pila:
        n = pila.pop()
        if n in comp or n in cadenas:
            continue
        comp.add(n)
        pila.extend(g["adj"].get(n, ()))
    return None if comp & g["grounded_seed"] else comp


def hoist_rules(doc, carga_kg: float | None = None) -> tuple[list[dict], set[str]]:
    """(reglas, pasadores verificados). `carga_kg`: la carga útil (los requisitos o el parámetro
    explícito de `/api/checks`), que se suma a CADA cuerpo colgado (conservador: con un contrapeso,
    también a él)."""
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.izaje_capacidad import REGLA, regla_capacidad_izaje
    from apolo.library.engineering.mass import feature_mass
    from apolo.library.peso_ficha import partes_de_cilindros
    from apolo.library.rules import _check

    cadenas = _cadenas_de_izaje(doc)
    if not cadenas:
        return [], set()
    ids_cadena = {fid for fid, _f, _l in cadenas}
    util = float(carga_kg or 0.0)
    partes = partes_de_cilindros(doc.scene)
    material = doc.default_material()
    masas: dict[str, float] = {}

    def masa(fid: str) -> float:
        if fid not in masas:
            masas[fid] = float(feature_mass(doc.scene[fid], CATALOG, material,
                                            partes.get(fid))["masa_kg"])
        return masas[fid]

    # el cuerpo de cada extremo: (clave, piezas) o None si no es determinable
    cuerpos: dict[tuple[str, str], tuple[str, frozenset] | None] = {}
    for fid, _f, lados in cadenas:
        for lado, (_pas, _ama, pieza) in lados.items():
            mov = _cuerpo_movil(doc.joints, pieza)
            if mov is not None:
                cuerpos[(fid, lado)] = (mov[0], frozenset(mov[1]))
                continue
            comp = _colgado_por_grafo(doc, pieza, ids_cadena)
            cuerpos[(fid, lado)] = None if comp is None else (pieza, frozenset(comp))
    # cuántas cadenas cuelgan cada cuerpo (una cadena con sus dos extremos en él cuenta una vez)
    por_cuerpo: dict[frozenset, set[str]] = {}
    for (fid, _lado), c in cuerpos.items():
        if c is not None:
            por_cuerpo.setdefault(c[1], set()).add(fid)

    reglas, verificados = [], set()
    for fid, f, lados in cadenas:
        nombre = f.name or fid
        comp = CATALOG.get(getattr(f, "component", None) or "")
        specs = (comp.specs if comp is not None else None) or {}
        if len(lados) < 2 or not specs.get("rotura_kN"):
            falta = ("sus dos amarres declarados ({id}_pasador_a|b y {id}_amarre_a|b de su comando)"
                     if len(lados) < 2 else "la rotura de la cadena en su ficha (specs.rotura_kN)")
            reglas.append({**_check(
                f"{REGLA} · {nombre}", "error",
                f"{nombre}: no se puede verificar la cadena de izaje — falta {falta}.",
                "Reconstruye la cadena con create_hoist_chain sin renombrar sus uniones."),
                "piezas": [fid]})
            continue
        extremos, vistos = [], set()
        for lado in "ab":
            c = cuerpos[(fid, lado)]
            if c is None:
                extremos = []
                break
            if c[1] in vistos:
                continue
            vistos.add(c[1])
            extremos.append({"cuerpo": doc.scene[c[0]].name or c[0],
                             "masa_kg": sum(masa(p) for p in c[1] if p in doc.scene),
                             "util_kg": util, "cadenas": len(por_cuerpo[c[1]])})
        regla = regla_capacidad_izaje(
            nombre, cadena=comp.ref, rotura_kn=float(specs["rotura_kN"]),
            kg_m=float(specs.get("kg_m") or comp.weight or 0.0),
            largo_mm=float(getattr(f, "cut_length", None) or 0.0), extremos=extremos,
            piezas=[fid, *(lados[k][2] for k in "ab")])
        if regla.pop("verificada"):
            verificados.update(lados[k][0] for k in "ab")
        reglas.append(regla)
    return reglas, verificados
