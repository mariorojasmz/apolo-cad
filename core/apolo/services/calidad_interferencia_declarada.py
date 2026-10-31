"""Mide el volumen común de cada par con unión DECLARADA (plan puerta-fuera-de-catalogo, D6): el
insumo de `union.interferencia_declarada`. El criterio (tolerancia, rosca engranada), en
`library/calidad/interferencia_declarada.py`.

La entrega excluye entero el par con `fasten` (`delivery_inputs.exclusiones_declaradas`); aquí se
mide sólo ESE par (nunca N²) con el mismo prefiltro exacto de `interference_report`
(`interferencias_filtro.Filtro`, con el umbral de la tolerancia: un par que no puede pasar de
`EXCESS_TOL_MM3` no gasta booleana). No se miden: la tornillería (de catálogo, `hardware_ids`; a
medida, `lints._is_bolt` o su rol de compra: la asienta su agujero o su ranura), el equipo de
catálogo de geometría REPRESENTATIVA (`FEA_HARDWARE_CATS`: motorreductor, variador, chumacera,
aparatos…; su sólido es una envolvente «a verificar con el proveedor», no la cota con que se
juzga un volumen: el NMRV-090 trae sus 6 pernos de brida dentro del sólido), el cable 3D
(`sin_medir`), los pares de junta (los mide la interpenetración en pose), lo que une una cadena (la
asienta su comando, `delivery_inputs.de_cadena`) ni lo oculto o de construcción (como la
interferencia de la entrega).

De cada solape se da, por SÓLIDO del volumen común, los pares de cilindros COAXIALES de radio
distinto que lo limitan (Ø exterior, Ø interior y largo a lo largo del eje): el anillo de una rosca
engranada se reconoce por ahí, sin mirar nombres. El llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

import math
import re

#: Dos caras cilíndricas son del mismo eje si sus ejes son paralelos y distan menos que esto (mm).
EJE_TOL_MM = 0.05
_PARALELO = 0.9999


#: Categorías de compra de la tornillería modelada a mano (`designacion_comercial`): perno,
#: espárrago, tuerca, arandela, anillo de retención (Seeger DIN 471/472, cuya ranura no se modela).
_CATEGORIAS_TORNILLERIA = frozenset({"pernos", "tuercas", "tornilleria"})
#: La tornillería de MADERA y chapa por su rol (anclado: «Taco del tirafondo» no es): rosca en su
#: agujero guía (el tirafondo 4,5×50 de la silla deja 269 mm³ en su guía de Ø3).
_ROL_TORNILLO_MADERA = re.compile(r"^(tirafondos?|autorroscantes?|autoperforantes?|clavos?)\b",
                                  re.I)


def sin_medir(doc) -> set[str]:
    """Las piezas a medida que no se miden, además de la tornillería de `exclusiones_declaradas`:
    la tornillería COMERCIAL por su rol de compra (el anillo Seeger asentado en una ranura que no
    se modela: 929,9 mm³ en el rodillo de cola del 38), la de madera por su rol
    (`_ROL_TORNILLO_MADERA`) y el CABLE 3D (material `cable`): un
    sustituto visual flexible del cable que cobra su `add_cable`, que cruza la chapa por su
    pasacables sin modelar."""
    from apolo.library.catalog import CATALOG
    from apolo.library.designacion_comercial import ROL_COMPRA, categoria_de_compra
    from apolo.library.materials import CABLE, piece_role, resolve_material

    vertical = doc.default_material()
    out = set()
    for fid, f in doc.scene.items():
        if getattr(f, "component", None):
            continue
        nombre = getattr(f, "name", None) or ""
        rol = piece_role(nombre)
        if (ROL_COMPRA.match(rol) and categoria_de_compra(nombre) in _CATEGORIAS_TORNILLERIA) \
                or _ROL_TORNILLO_MADERA.match(rol):
            out.add(fid)
        elif resolve_material(f, CATALOG, vertical) == CABLE:
            out.add(fid)
    return out


def _volumen(shape) -> float:
    try:
        return sum(float(s.volume) for s in _solidos_de(shape))
    except Exception:  # noqa: BLE001 — sin volumen legible: no se toma por contenida
        return 0.0


def _medible(feat) -> bool:
    return (feat is not None and getattr(feat, "shape", None) is not None
            and getattr(feat, "visible", True) and not getattr(feat, "is_guide", False))


def _cilindros(solido) -> list[tuple[tuple, tuple, float, list]]:
    """[(dirección unitaria, punto del eje, radio, vértices de la cara)] de las caras cilíndricas."""
    from build123d import GeomType
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    out = []
    for cara in solido.faces():
        if cara.geom_type != GeomType.CYLINDER:
            continue
        cyl = BRepAdaptor_Surface(cara.wrapped).Cylinder()
        dd, loc = cyl.Axis().Direction(), cyl.Axis().Location()
        n = math.sqrt(dd.X() ** 2 + dd.Y() ** 2 + dd.Z() ** 2) or 1.0
        out.append(((dd.X() / n, dd.Y() / n, dd.Z() / n), (loc.X(), loc.Y(), loc.Z()),
                    cyl.Radius(), [(v.X, v.Y, v.Z) for v in cara.vertices()]))
    return out


def _sobre_la_recta(d, p0, p) -> bool:
    w = (p[0] - p0[0], p[1] - p0[1], p[2] - p0[2])
    t = w[0] * d[0] + w[1] * d[1] + w[2] * d[2]
    return math.sqrt(max(0.0, w[0] ** 2 + w[1] ** 2 + w[2] ** 2 - t * t)) < EJE_TOL_MM


def anillos(solido) -> list[dict]:
    """Los anillos coaxiales que limitan un sólido: por cada recta con caras cilíndricas de ≥ 2
    radios distintos, {d_ext, d_int, largo_mm} (radio mayor y menor; largo = la extensión de esas
    caras a lo largo del eje)."""
    rectas: list[list] = []  # [dirección, punto, {radios}, vértices]
    for d, p, r, verts in _cilindros(solido):
        for recta in rectas:
            if abs(sum(a * b for a, b in zip(recta[0], d))) >= _PARALELO and \
                    _sobre_la_recta(recta[0], recta[1], p):
                recta[2].add(round(r, 3))
                recta[3].extend(verts)
                break
        else:
            rectas.append([d, p, {round(r, 3)}, list(verts)])
    out = []
    for d, p, radios, verts in rectas:
        if len(radios) < 2 or not verts:
            continue
        ts = [sum((v[i] - p[i]) * d[i] for i in range(3)) for v in verts]
        out.append({"d_ext": round(2 * max(radios), 3), "d_int": round(2 * min(radios), 3),
                    "largo_mm": round(max(ts) - min(ts), 3)})
    return out


def _solidos_de(inter) -> list:
    """Los sólidos de una intersección: build123d da una forma o, si las partes son disjuntas o
    una de las piezas es una ShapeList, una `ShapeList` de formas."""
    if inter is None:
        return []
    if hasattr(inter, "solids"):
        return list(inter.solids())
    return [s for parte in inter for s in _solidos_de(parte)]


def _solidos(solidos: list) -> list[dict]:
    out = []
    for s in solidos:
        try:
            an = anillos(s)
        except Exception:  # noqa: BLE001 — sin anillos legibles: todo su volumen cuenta
            an = []
        out.append({"volumen_mm3": round(float(s.volume), 1), "anillos": an})
    return out


def interferencia_declarada(doc) -> dict | None:
    """{pares, solapes, errores} de los pares con `fasten` entre piezas que no son tornillería, o
    None si el modelo no declara uniones. `solapes`: los pares con más de `EXCESS_TOL_MM3` en
    común, {a, b, nombre_a, nombre_b, uniones, kinds, volumen_mm3, solidos}; `errores`: los pares
    que OCCT no pudo intersecar ({a, b, error})."""
    if not doc.fasteners:
        return None
    from apolo.kernel.caja import caja as caja_optima
    from apolo.library.checks import EXCESS_TOL_MM3, FEA_HARDWARE_CATS, hardware_ids, joint_pairs
    from apolo.library.interferencias_filtro import Filtro, caja

    from .delivery_inputs import de_cadena, exclusiones_declaradas

    _pares_fasten, bolt_ids = exclusiones_declaradas(doc)
    fuera = hardware_ids(doc, FEA_HARDWARE_CATS) | bolt_ids | sin_medir(doc)
    de_junta = joint_pairs(doc)
    es_de_cadena = de_cadena(doc)
    pares: dict[frozenset, dict] = {}
    for nombre, f in sorted(doc.fasteners.items()):
        a, b = f.get("a"), f.get("b")
        if a == b or a in fuera or b in fuera:
            continue
        fa, fb = doc.scene.get(a), doc.scene.get(b)
        par = frozenset((a, b))
        if not (_medible(fa) and _medible(fb)) or par in de_junta or es_de_cadena(f):
            continue
        fila = pares.setdefault(par, {"a": a, "b": b, "nombre_a": fa.name, "nombre_b": fb.name,
                                      "catalogo_a": bool(getattr(fa, "component", None)),
                                      "catalogo_b": bool(getattr(fb, "component", None)),
                                      "uniones": [], "kinds": []})
        fila["uniones"].append(nombre)
        fila["kinds"].append(f.get("kind", "perno"))
    filtro, cajas = Filtro(), {}

    def caja_de(fid):
        if fid not in cajas:
            cajas[fid] = caja(caja_optima(doc.scene[fid].shape))
        return cajas[fid]

    solapes, errores = [], []
    for fila in pares.values():
        sa, sb = doc.scene[fila["a"]].shape, doc.scene[fila["b"]].shape
        try:
            if not filtro.puede_interferir(sa, sb, caja_de(fila["a"]), caja_de(fila["b"]),
                                           EXCESS_TOL_MM3):
                continue
            solidos = _solidos_de(sa & sb)
            v = sum(float(s.volume) for s in solidos)
        except Exception as exc:  # noqa: BLE001 — OCCT no pudo: el par lo dice (no es OK)
            errores.append({"a": fila["a"], "b": fila["b"],
                            "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        if v > EXCESS_TOL_MM3:
            solapes.append({**fila, "volumen_mm3": round(v, 1), "solidos": _solidos(solidos),
                            "volumen_a_mm3": round(_volumen(sa), 1),
                            "volumen_b_mm3": round(_volumen(sb), 1)})
    solapes.sort(key=lambda s: -s["volumen_mm3"])
    return {"pares": len(pares), "solapes": solapes, "errores": errores}
