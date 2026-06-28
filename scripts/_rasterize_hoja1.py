"""One-off: rasteriza a PNG la MISMA lámina que /api/drawing/spec produjo para la Hoja 1,
para inspeccionarla visualmente (no hay pdftoppm/fitz). Usa pdf._figure → savefig PNG."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apolo.projects import ProjectStore
from apolo.drawing import compose_sheet
from apolo.drawing.pdf import _figure

DB = ROOT / "data" / "apolo.db"
PID = 28
# 5 tablas de la hoja + las 3 bisagras del canto (herraje: cut_list las excluye del despiece,
# pero el detalle del larguero necesita sus posiciones, y se ven en el alzado).
ISOLATE = ["c85", "c337", "c40", "c338", "c42", "c245", "c241", "c237"]

store = ProjectStore(str(DB))
doc = store.load(PID)
scene = {fid: doc.scene[fid] for fid in ISOLATE if fid in doc.scene}
print("solidos aislados:", list(scene.keys()))

# replica _drawing_meta (revisiones del cajetin)
revs = store.list_revisions(PID)
meta = {
    "drawing_no": "PLG-H1-001",
    "material": "Madera",
    "title": "Hoja 1 - puerta plegable",
    "revisions": [
        {"rev": i + 1, "date": r.get("created_at", r.get("date", "")), "note": r.get("note", "")}
        for i, r in enumerate(revs)
    ],
}

model = compose_sheet(
    scene, sheet="A3", include_hidden=False, project_name=doc.name,
    cutlist=True, section="y",
    datum_dims=["c338", "c40", "c337"],  # ubicación de los 3 travesaños desde la base
    member_detail={"member": "c85", "pick": [18, 100, 2008],
                   "locate": ["c245", "c241", "c237"], "scale": 0, "name": "H1 larguero"},
    meta=meta,
)

fig = _figure(model)
out = ROOT / "planos" / "hoja1-plano.png"
fig.savefig(str(out), dpi=200)
print("PNG:", out)
