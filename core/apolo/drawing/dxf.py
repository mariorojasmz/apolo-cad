"""Exportador DXF de la lámina (ezdxf, R2010)."""

from __future__ import annotations

import io

from ..library.materials import hatch_pattern
from .esquema import CAPA_DXF, ESTILOS, LINEWEIGHT_DXF, LLENO, PILOTAJE, TIPO_LINEA_DXF, trazos_mm
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
    "thread": ("ROSCA", 3, "CONTINUOUS", 13),  # cosmético ISO 6410: trazo FINO
}
# trazos de esquema (`esquema.py`): una capa propia, que sólo se crea si la lámina la usa (una
# lámina mecánica sale igual que antes)
CAPA_ESQUEMA = (CAPA_DXF, 7, "CONTINUOUS", LINEWEIGHT_DXF)


def _usa_esquema(model: SheetModel) -> bool:
    return any(x.kind in ESTILOS for x in (*model.lines, *model.circles, *model.polygons))


def _lleno(msp, borde: list[tuple[float, float]]) -> None:
    """Relleno sólido negro (ACI 7) de un contorno de esquema, en su capa."""
    hh = msp.add_hatch(color=7, dxfattribs={"layer": CAPA_DXF})
    hh.set_solid_fill(color=7)
    hh.paths.add_polyline_path(borde, is_closed=True)


def sheet_to_dxf(model: SheetModel) -> bytes:
    import ezdxf

    doc = ezdxf.new("R2010", setup=True)  # setup=True carga los tipos de línea estándar
    doc.header["$LWDISPLAY"] = 1  # mostrar grosores de línea
    msp = doc.modelspace()
    for name, color, linetype, lw in (*LAYERS.values(), *([CAPA_ESQUEMA] if _usa_esquema(model) else [])):
        if name not in doc.layers:
            doc.layers.add(name, color=color, linetype=linetype, lineweight=lw)
    if any(x.kind == PILOTAJE for x in model.lines):  # la línea a trazos del esquema (V8.9 F5)
        trazo, hueco = trazos_mm()
        doc.linetypes.add(TIPO_LINEA_DXF, pattern=[trazo + hueco, trazo, -hueco],
                          description="Esquema: trazos 12d/3d (ISO 128-20 tipo 02)")

    for line in model.lines:
        layer = CAPA_DXF if line.kind in ESTILOS else LAYERS.get(line.kind, LAYERS["visible"])[0]
        attribs = {"layer": layer, **({"linetype": TIPO_LINEA_DXF} if line.kind == PILOTAJE else {})}
        msp.add_line((line.x1, line.y1), (line.x2, line.y2), dxfattribs=attribs)

    for poly in model.polygons:
        if poly.kind in ESTILOS:  # contorno de símbolo; con `LLENO`, además el relleno sólido
            if poly.kind == LLENO:
                _lleno(msp, poly.rings[0])
            for ring in poly.rings:
                msp.add_lwpolyline(ring, close=True, dxfattribs={"layer": CAPA_DXF})
            continue
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
        if c.kind in ESTILOS:  # círculo de símbolo; el punto de unión, además relleno
            if c.kind == LLENO:
                hh = msp.add_hatch(color=7, dxfattribs={"layer": CAPA_DXF})
                hh.set_solid_fill(color=7)
                hh.paths.add_edge_path().add_arc((c.x, c.y), c.r, 0.0, 360.0)
            msp.add_circle((c.x, c.y), c.r, dxfattribs={"layer": CAPA_DXF})
            continue
        layer = "CORTE" if c.kind == "corte" else "COTAS"
        msp.add_circle((c.x, c.y), c.r, dxfattribs={"layer": layer})

    for a in model.arcs:
        layer = LAYERS.get(a.kind, LAYERS["thread"])[0]
        msp.add_arc((a.x, a.y), a.r, a.a1, a.a2, dxfattribs={"layer": layer})

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
