"""Cotas de INTERFAZ / patrón de montaje (pitch centro-a-centro + luz total).

A diferencia de auto_dims (posición desde el datum, para FABRICAR), interface_dims acota el
pitch entre agujeros — lo que un montador necesita para taladrar la placa de acople — y NO debe
solaparse con las escaleras de auto_dims cuando ambos están activos.
"""

from apolo.doc import Document
from apolo.drawing import compose_sheet


def _placa_patron(doc: Document) -> str:
    """Placa 240×120×20 con 6 agujeros Ø11 en rejilla 3×2 (x=-80,0,80 · y=-40,40)."""
    cid = doc.execute("create_box", {"name": "placa", "width": 240, "depth": 120, "height": 20})
    for x in (-80, 0, 80):
        for y in (-40, 40):
            doc.execute("drill_hole", {"feature": cid, "position": {"x": x, "y": y, "z": -10},
                                       "axis": "z", "diameter": 11, "depth": 0})
    return cid


def _bbox(lab):
    w = max(len(lab.text), 1) * lab.size * 0.52
    h = lab.size
    if 45 < abs(lab.rotation) % 180 < 135:  # texto vertical → intercambia ancho/alto
        w, h = h, w
    x0 = lab.x - w / 2 if lab.anchor == "middle" else (lab.x - w if lab.anchor == "end" else lab.x)
    return (x0, lab.y - 0.3 * lab.size, x0 + w, lab.y + 0.8 * lab.size)


def _overlaps(model, *, min_area=2.0, min_frac=0.25):
    labs = [(l, _bbox(l)) for l in model.labels if l.text.strip()]
    hits = []
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            (la, ba), (lb, bb) = labs[i], labs[j]
            ix = max(0.0, min(ba[2], bb[2]) - max(ba[0], bb[0]))
            iy = max(0.0, min(ba[3], bb[3]) - max(ba[1], bb[1]))
            ar = ix * iy
            if ar < min_area:
                continue
            aa = (ba[2] - ba[0]) * (ba[3] - ba[1]) or 1
            ab = (bb[2] - bb[0]) * (bb[3] - bb[1]) or 1
            if ar / min(aa, ab) >= min_frac:
                hits.append((la.text, lb.text, round(ar, 1)))
    return hits


def test_interface_dims_emit_pitch_and_span():
    doc = Document()
    _placa_patron(doc)
    base = [l.text for l in compose_sheet(doc.scene).labels]
    iface = [l.text for l in compose_sheet(doc.scene, interface_dims=True).labels]
    # pitch (80) y luz total en X (160) — el span 160 NO es una cota general (la placa mide 240×120)
    assert "160" not in base and "160" in iface   # luz total del patrón en X
    assert "80" in iface                           # pitch entre columnas/filas
    # añade cotas: más líneas de cota que la lámina base
    n_base = sum(1 for l in compose_sheet(doc.scene).lines if l.kind == "dim")
    n_iface = sum(1 for l in compose_sheet(doc.scene, interface_dims=True).lines if l.kind == "dim")
    assert n_iface > n_base


def test_interface_and_auto_dims_do_not_overlap():
    """auto_dims (posición desde datum) + interface_dims (pitch) en la misma vista → 0 solapes."""
    doc = Document()
    _placa_patron(doc)
    model = compose_sheet(doc.scene, auto_dims=True, interface_dims=True)
    hits = _overlaps(model)
    assert hits == [], f"solapes de texto inesperados: {hits[:5]}"


def test_interface_dims_noop_without_holes():
    doc = Document()
    doc.execute("create_box", {"name": "bloque", "width": 100, "depth": 60, "height": 40})
    a = sum(1 for l in compose_sheet(doc.scene).lines if l.kind == "dim")
    b = sum(1 for l in compose_sheet(doc.scene, interface_dims=True).lines if l.kind == "dim")
    assert a == b  # sin agujeros, no añade cotas de patrón
