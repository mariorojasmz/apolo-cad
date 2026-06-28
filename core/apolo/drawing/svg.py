"""Exportador SVG de la lámina."""

from __future__ import annotations

import base64
from xml.sax.saxutils import escape

from ..library.materials import hatch_pattern
from .sheet import SheetModel

# patrones de rayado de sección por material (tile en userSpaceOnUse, mm)
HATCH_DEFS = (
    '<defs>'
    '<pattern id="h_ansi31" width="2.2" height="2.2" patternUnits="userSpaceOnUse" '
    'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="2.2" stroke="#16181d" stroke-width="0.18"/></pattern>'
    '<pattern id="h_madera" width="3.6" height="3.6" patternUnits="userSpaceOnUse" '
    'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="3.6" stroke="#9a6a3a" stroke-width="0.22"/></pattern>'
    '<pattern id="h_vidrio" width="1.3" height="1.3" patternUnits="userSpaceOnUse">'
    '<line x1="0" y1="0" x2="0" y2="1.3" stroke="#5a8aa0" stroke-width="0.12"/></pattern>'
    '</defs>'
)

STYLES = {
    "visible": 'stroke="#16181d" stroke-width="0.5"',
    "hidden": 'stroke="#7a8290" stroke-width="0.3" stroke-dasharray="2.2,1.4"',
    "frame": 'stroke="#16181d" stroke-width="0.75"',
    "dim": 'stroke="#3a5e9c" stroke-width="0.25"',
    "center": 'stroke="#b0413e" stroke-width="0.25" stroke-dasharray="6,1.5,1,1.5"',
}
ANCHORS = {"start": "start", "middle": "middle", "end": "end"}


def sheet_to_svg(model: SheetModel) -> str:
    h = model.height

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {model.width} {model.height}" '
        f'width="{model.width}mm" height="{model.height}mm" font-family="Segoe UI, Arial, sans-serif">',
        f'<rect x="0" y="0" width="{model.width}" height="{model.height}" fill="#fdfdfb"/>',
        HATCH_DEFS,
    ]
    for img in model.images:  # render raster embebido (iso sombreado a color)
        b64 = base64.b64encode(img.png).decode("ascii")
        parts.append(
            f'<image x="{img.x:.2f}" y="{h - img.y - img.h:.2f}" width="{img.w:.2f}" '
            f'height="{img.h:.2f}" preserveAspectRatio="xMidYMid meet" '
            f'href="data:image/png;base64,{b64}"/>'
        )
    for poly in model.polygons:  # caras de corte: rayado por material bajo las aristas
        d = ""
        for ring in poly.rings:
            d += "M " + " L ".join(f"{x:.2f} {h - y:.2f}" for x, y in ring) + " Z "
        fill = f"url(#h_{hatch_pattern(poly.material)})" if poly.material else "#ccd5e3"
        parts.append(
            f'<path d="{d.strip()}" fill="{fill}" stroke="#16181d" stroke-width="0.4" fill-rule="evenodd"/>'
        )
    for line in model.lines:
        style = STYLES.get(line.kind, STYLES["visible"])
        parts.append(
            f'<line x1="{line.x1:.2f}" y1="{h - line.y1:.2f}" '
            f'x2="{line.x2:.2f}" y2="{h - line.y2:.2f}" {style} stroke-linecap="round"/>'
        )
    for c in model.circles:
        if c.kind == "corte":  # taladro: trazo de corte, sin relleno
            parts.append(
                f'<circle cx="{c.x:.2f}" cy="{h - c.y:.2f}" r="{c.r:.2f}" '
                f'fill="none" stroke="#c0392b" stroke-width="0.5"/>'
            )
        else:  # globos de BOM / cotas
            parts.append(
                f'<circle cx="{c.x:.2f}" cy="{h - c.y:.2f}" r="{c.r:.2f}" '
                f'fill="#fdfdfb" stroke="#3a5e9c" stroke-width="0.4"/>'
            )
    for lab in model.labels:
        x, y = lab.x, h - lab.y
        transform = f' transform="rotate(-{lab.rotation:g} {x:.2f} {y:.2f})"' if lab.rotation else ""
        parts.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="{lab.size}" fill="#16181d" '
            f'text-anchor="{ANCHORS.get(lab.anchor, "middle")}"{transform}>{escape(lab.text)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)
