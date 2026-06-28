"""Detector de solapes de TEXTO en las láminas: estima la caja de cada Label y reporta pares
que se pisan de forma significativa. No es exacto (aproxima el ancho del texto), pero caza los
solapes reales (texto sobre texto / sobre cajetín)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apolo.doc import Document
from apolo.drawing import compose_sheet, sheet_set
from apolo.projects import ProjectStore


def _bbox(lab):
    w = max(len(lab.text), 1) * lab.size * 0.52
    h = lab.size
    rot = abs(lab.rotation) % 180
    if 45 < rot < 135:  # texto vertical → intercambia ancho/alto
        w, h = h, w
    if lab.anchor == "middle":
        x0 = lab.x - w / 2
    elif lab.anchor == "end":
        x0 = lab.x - w
    else:
        x0 = lab.x
    return (x0, lab.y - 0.3 * lab.size, x0 + w, lab.y + 0.8 * lab.size)


def _overlap_area(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def overlaps(model, *, min_area=2.0, min_frac=0.25):
    labs = [(lab, _bbox(lab)) for lab in model.labels if lab.text.strip()]
    hits = []
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            la, ba = labs[i]
            lb, bb = labs[j]
            ar = _overlap_area(ba, bb)
            if ar < min_area:
                continue
            area_a = (ba[2] - ba[0]) * (ba[3] - ba[1]) or 1
            area_b = (bb[2] - bb[0]) * (bb[3] - bb[1]) or 1
            if ar / min(area_a, area_b) >= min_frac:
                hits.append((f"{la.text[:18]}@({la.x:.0f},{la.y:.0f})r{la.rotation:.0f}",
                             f"{lb.text[:18]}@({lb.x:.0f},{lb.y:.0f})r{lb.rotation:.0f}", round(ar, 1)))
    return hits


def report(name, model):
    hits = overlaps(model)
    tag = "OK" if not hits else f"{len(hits)} SOLAPES"
    print(f"[{tag}] {name}")
    for a, b, ar in hits[:8]:
        print(f"     {a}  x  {b}   ({ar} mm2)")


store = ProjectStore(str(ROOT / "data" / "apolo.db"))
doc = store.load(28)
revs = store.list_revisions(28)
meta = {"drawing_no": "PLG-001",
        "revisions": [{"rev": i + 1, "date": r.get("created_at", ""), "note": r.get("note", "")}
                      for i, r in enumerate(revs)]}

# 1) las 14 páginas del juego de la puerta (el caso real)
for k, pg in enumerate(sheet_set(doc.scene, project_name="Puerta", template="carpinteria", meta=meta)):
    report(f"juego pag {k:02d}", pg)

# 2) casos sintéticos variados
d = Document()
cid = d.execute("create_box", {"name": "brida", "width": 200, "depth": 120, "height": 20})
for x, y in ((-70, -40), (70, -40), (-70, 40), (70, 40)):
    d.execute("drill_hole", {"feature": cid, "position": {"x": x, "y": y, "z": -10}, "axis": "z", "diameter": 11, "depth": 0})
report("brida auto_dims", compose_sheet(d.scene, auto_dims=True, meta=meta))
report("brida explode", compose_sheet(d.scene, explode={"axis": "z"}, meta=meta))
report("brida notas", compose_sheet(d.scene, notes=["Romper aristas", "Acabado granallado", "ISO 2768-m"], meta=meta))
report("puerta conjunto", compose_sheet(doc.scene, cutlist=True, hardware=True, meta=meta))
