"""Checkpoint Fase 1: rasteriza páginas clave del JUEGO de planos de la puerta (id 28)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from apolo.projects import ProjectStore
from apolo.drawing import sheet_set
from apolo.drawing.pdf import _figure

store = ProjectStore(str(ROOT / "data" / "apolo.db"))
doc = store.load(28)
revs = store.list_revisions(28)
meta = {"drawing_no": "PLG-001",
        "revisions": [{"rev": i + 1, "date": r.get("created_at", ""), "note": r.get("note", "")}
                      for i, r in enumerate(revs)]}

pages = sheet_set(doc.scene, project_name="Puerta plegable", template="carpinteria", meta=meta)
print("paginas:", len(pages))

# guarda las páginas clave: conjunto (0), 1ª pieza (1), y las 2 últimas (corte + herraje)
keys = {0: "conjunto", 1: "pieza1", len(pages) - 2: "corte", len(pages) - 1: "herraje"}
out = ROOT / "planos"
for idx, name in keys.items():
    fig = _figure(pages[idx])
    p = out / f"juego_{idx:02d}_{name}.png"
    fig.savefig(str(p), dpi=80)
    print("PNG:", p.name)
