"""Exportador DXF de la lámina (ezdxf, R2010)."""

from __future__ import annotations

import io

from ..library.materials import hatch_pattern
from .sheet import SheetModel

# rayado ANSI31 con escala/color por material (ANSI31 existe siempre en ezdxf)
HATCH_SCALE = {"ansi31": 1.0, "madera": 2.5, "vidrio": 0.6}
HATCH_COLOR = {"ansi31": 8, "madera": 30, "vidrio": 4}

# (capa, color ACI, tipo de línea, lineweight en 1/100 mm)
LAYERS = {
    "visible": ("VISIBLE", 7, "CONTINUOUS", 50),
    "hidden": ("OCULTA", 8, "DASHED", 35),
    "frame": ("MARCO", 7, "CONTINUOUS", 70),
    "dim": ("COTAS", 5, "CONTINUOUS", 25),
    "center": ("EJES", 1, "CENTER", 25),
    "corte": ("CORTE", 4, "CONTINUOUS", 35),
}


def sheet_to_dxf(model: SheetModel) -> bytes:
    import ezdxf

    doc = ezdxf.new("R2010", setup=True)  # setup=True carga los tipos de línea estándar
    doc.header["$LWDISPLAY"] = 1  # mostrar grosores de línea
    msp = doc.modelspace()
    for name, color, linetype, lw in LAYERS.values():
        if name not in doc.layers:
            doc.layers.add(name, color=color, linetype=linetype, lineweight=lw)

    for line in model.lines:
        layer = LAYERS.get(line.kind, LAYERS["visible"])[0]
        msp.add_line((line.x1, line.y1), (line.x2, line.y2), dxfattribs={"layer": layer})

    for poly in model.polygons:
        if poly.material:
            pat = hatch_pattern(poly.material)
            try:
                hh = msp.add_hatch(color=HATCH_COLOR.get(pat, 8), dxfattribs={"layer": "CORTE"})
                hh.set_pattern_fill("ANSI31", scale=HATCH_SCALE.get(pat, 1.0))
                for ring in poly.rings:
                    hh.paths.add_polyline_path(ring, is_closed=True)
            except Exception:
                pass
        for ring in poly.rings:
            msp.add_lwpolyline(ring, close=True, dxfattribs={"layer": "CORTE"})

    for c in model.circles:
        layer = "CORTE" if c.kind == "corte" else "COTAS"
        msp.add_circle((c.x, c.y), c.r, dxfattribs={"layer": layer})

    for lab in model.labels:
        msp.add_text(
            lab.text,
            dxfattribs={
                "layer": "COTAS",
                "height": lab.size,
                "rotation": lab.rotation,
                "insert": (lab.x, lab.y),
            },
        )

    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")
