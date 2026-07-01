"""Rasteriza la memoria de cálculo sintética a PNG (verificación visual)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from apolo.doc.document import Document  # noqa: E402
from apolo.drawing.calc_report import calc_report  # noqa: E402
from apolo.drawing.pdf import _figure  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_calc_report import REQ, RULES, _scene  # noqa: E402

from apolo.kernel.render import render_scene_png  # noqa: E402

doc = Document("faja-demo")
doc.execute("create_box", {"name": "Tambor motriz", "width": 114, "depth": 600, "height": 114,
                           "position": {"x": 0, "y": 0, "z": 400}})
doc.execute("create_box", {"name": "Larguero 80x40x3", "width": 2000, "depth": 40, "height": 80,
                           "position": {"x": 0, "y": 300, "z": 300}})
png = render_scene_png(doc.scene, view="iso", size_px=620, clean=True)

pages = calc_report(doc.scene, rules=RULES, requirements=REQ,
                    project_name="Faja de banda 4 m", png=png)
out = Path(__file__).parent
for i, name in ((0, "_memoria_portada.png"), (1, "_memoria_seccion.png"), (3, "_memoria_misc.png")):
    fig = _figure(pages[i])
    fig.savefig(out / name, dpi=110)
print("ok", len(pages), "páginas")
