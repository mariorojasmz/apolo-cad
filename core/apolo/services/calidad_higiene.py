"""Las rendijas y los tubos abiertos de un equipo higiénico (plan hallazgos-del-revisor-en-la-puerta,
D9): el insumo de `higiene.limpiable` (`library/calidad/higiene.py`, donde está el criterio). Sólo
se mide con el requisito `higienico` (`requisitos.es_higienico`): sin él, nada. El llamador
sostiene STATE_LOCK.

- **Soldaduras**: las filas de `calidad_contacto.uniones_medidas` (las que ya midió la entrega, si
  se pasan: no se re-mide) con su línea de contacto, su largo declarado y si la nota del `fasten`
  declara el sellado sanitario.
- **Tubos**: cada pieza que se FABRICA (sin tornillería, sin compra declarada; de catálogo sólo un
  perfil `cuttable`) y cada extremo hueco suyo: una cara plana con un hueco que es ≥ `FRACCION_HUECO`
  de su sección, en una pieza más larga que ancha a lo largo de la normal y hueca hasta la mitad de
  ese largo (un agujero de perno en una placa, un roscado ciego en un casquillo o un buje grueso no
  son tubos). El extremo está CERRADO si cada punto del borde de su hueco queda a <
  `HOLGURA_LIMPIABLE_MM` de una pieza SOLDADA al tubo: una tapa, la cara a la que llega a tope o el
  otro tubo de un inglete (sus huecos se comunican y cada extremo del otro se juzga aparte).
"""

from __future__ import annotations

from apolo.library.calidad.higiene import FORMAS_LINEALES, HOLGURA_LIMPIABLE_MM, sellado_sanitario

#: Un hueco que ocupa menos de esto de la sección de su cara es un agujero, no la luz de un tubo
#: (el Ø8,5 roscado de un casquillo Ø30: 0,08; un tubo 40×40×1,5: 0,86; un Sch 160 de Ø60: 0,44).
FRACCION_HUECO = 0.3
#: Puntos del borde del hueco que se comprueban (el borde entero, a pasos iguales).
MUESTRAS = 12


def requiere(doc) -> bool:
    from apolo.library.requisitos import es_higienico

    return es_higienico(getattr(doc, "requirements", None))


def higiene(doc, uniones: list[dict] | None = None) -> dict | None:
    """El insumo de `higiene.limpiable` (formato en `calidad/higiene.limpiable`), o None sin el
    requisito. `uniones` = las filas que ya midió la entrega (todas las uniones)."""
    if not requiere(doc):
        return None
    if uniones is None:
        from .calidad_contacto import uniones_medidas

        uniones = uniones_medidas(doc, ("soldadura",)) or []
    soldaduras, sin_medir, otras = [], [], 0
    for f in uniones:
        if f.get("kind") != "soldadura" or f.get("forma") == "de_su_comando":
            continue
        if f.get("error"):
            sin_medir.append({"que": f"soldadura {f['union']}", "piezas": [f["a"], f["b"]],
                              "motivo": f["error"]})
            continue
        if f.get("forma") not in FORMAS_LINEALES or not float(f.get("cordon_mm") or 0.0) > 0:
            otras += 1  # sin línea: lo juzga union.contacto_real
            continue
        nota = (doc.fasteners.get(f["union"]) or {}).get("nota") or ""
        soldaduras.append({k: f.get(k) for k in ("union", "a", "b", "nombre_a", "nombre_b",
                                                 "cordon_mm", "largo_declarado_mm")}
                          | {"sellado": sellado_sanitario(nota), "nota": nota[:120]})
    tubos = []
    soldadas = _soldadas(doc)
    for fid in _candidatos(doc):
        feat = doc.scene[fid]
        try:
            extremos = extremos_huecos(feat.shape)
            abiertos = [e for e in extremos if not _cerrado(e, [doc.scene[v].shape for v in
                                                                 soldadas.get(fid, ())
                                                                 if v in doc.scene])]
        except Exception as exc:  # noqa: BLE001 — OCCT no pudo: SIN_EVALUAR, nunca OK
            sin_medir.append({"que": f"tubo {feat.name}", "piezas": [fid],
                              "motivo": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        if extremos:
            tubos.append({"id": fid, "nombre": feat.name, "extremos": len(extremos),
                          "abiertos": [{k: e[k] for k in ("centro", "normal", "ancho_mm",
                                                          "holgura_mm")} for e in abiertos]})
    return {"soldaduras": soldaduras, "otras_formas": otras, "tubos": tubos,
            "sin_medir": sin_medir}


def _soldadas(doc) -> dict[str, set]:
    """{pieza: las piezas soldadas a ella} (las uniones `soldadura` declaradas)."""
    out: dict[str, set] = {}
    for f in doc.fasteners.values():
        if f.get("kind") == "soldadura":
            out.setdefault(f.get("a"), set()).add(f.get("b"))
            out.setdefault(f.get("b"), set()).add(f.get("a"))
    return out


def _candidatos(doc) -> list[str]:
    """Las piezas que se fabrican y podrían ser un tubo de la estructura."""
    from apolo.kernel.shapes import is_surface
    from apolo.library.catalog import CATALOG
    from apolo.library.designacion_comercial import es_comercial
    from apolo.library.lints import _is_bolt

    out = []
    for fid, f in doc.scene.items():
        if getattr(f, "is_guide", False) or getattr(f, "shape", None) is None:
            continue
        ref = getattr(f, "component", None)
        comp = CATALOG.get(ref) if ref else None
        if ref and (comp is None or not comp.cuttable):
            continue  # una ref que se compra: su diseño es del fabricante
        if _is_bolt(f, CATALOG) or (not ref and es_comercial(f.name)) or is_surface(f.shape):
            continue
        out.append(fid)
    return out


def extremos_huecos(shape) -> list[dict]:
    """Los extremos huecos de un tubo: {centro, normal (hacia afuera), ancho_mm, borde: [puntos
    del borde del hueco]}; [] si la pieza no es un tubo."""
    from build123d import Face, GeomType

    vs = [v.center() for v in shape.vertices()]
    out = []
    for cara in shape.faces():
        if cara.geom_type != GeomType.PLANE:
            continue
        for w in cara.inner_wires():
            hueco = Face(w)
            if hueco.area < FRACCION_HUECO * (hueco.area + cara.area):
                continue
            c, n = hueco.center(), cara.normal_at(cara.center())
            proy = [v.dot(n) for v in vs]
            s0, smin, smax = c.dot(n), min(proy), max(proy)
            if abs(s0 - smin) < abs(s0 - smax):
                n, smin, smax, s0 = -n, -smax, -smin, -s0  # la normal hacia afuera del tubo
            largo, bb = smax - smin, hueco.bounding_box()
            ancho = max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
            borde = [w.position_at(k / MUESTRAS) for k in range(MUESTRAS)]
            if largo < ancho or not _hueco(shape, c, n, borde, largo):
                continue  # más ancho que largo, o la luz no está vacía: no es un tubo
            out.append({"centro": [round(c.X, 1), round(c.Y, 1), round(c.Z, 1)],
                        "normal": [round(n.X, 3), round(n.Y, 3), round(n.Z, 3)],
                        "ancho_mm": round(ancho, 1), "borde": borde})
    return out


def _hueco(shape, c, n, borde, largo: float) -> bool:
    """¿La luz está VACÍA a los dos lados de la cara y hasta la mitad del largo? En el centro y a
    medio camino del borde (un roscado ciego en el centro de un casquillo, o el escalón donde
    nace un cilindro de una placa, tienen material ahí)."""
    puntos = [c] + [c + (borde[k] - c) * 0.5 for k in range(0, MUESTRAS, MUESTRAS // 4)]
    return not any(_dentro(shape, q + n * d) for q in puntos
                   for d in (1.0, -1.0, -largo / 2.0))


def _dentro(shape, p) -> bool:
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON

    for s in shape.solids():
        estado = BRepClass3d_SolidClassifier(s.wrapped, gp_Pnt(p.X, p.Y, p.Z), 1e-6).State()
        if estado in (TopAbs_IN, TopAbs_ON):
            return True
    return False


def _cerrado(extremo: dict, vecinas: list) -> bool:
    """¿Cada punto del borde del hueco queda a < la holgura limpiable de una pieza soldada? Anota
    en el extremo la mayor holgura medida (`holgura_mm`: el punto del borde más lejos de toda pieza
    soldada; None sin piezas soldadas cerca)."""
    from build123d import Vertex

    lim = HOLGURA_LIMPIABLE_MM
    cerca = [s for s in vecinas if _caja_cerca(s, extremo["borde"], lim)]
    if not cerca:
        extremo["holgura_mm"] = None
        return False
    peor = max(min(Vertex(p.X, p.Y, p.Z).distance_to(s) for s in cerca)
               for p in extremo["borde"])
    extremo["holgura_mm"] = round(peor, 2)
    return peor < lim


def _caja_cerca(shape, puntos, margen: float) -> bool:
    bb = shape.bounding_box()
    return any(bb.min.X - margen <= p.X <= bb.max.X + margen and
               bb.min.Y - margen <= p.Y <= bb.max.Y + margen and
               bb.min.Z - margen <= p.Z <= bb.max.Z + margen for p in puntos)
