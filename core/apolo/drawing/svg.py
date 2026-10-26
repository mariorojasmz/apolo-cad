"""Exportador SVG de la lámina.

La letra sale del MISMO tamaño que en el PDF (V8.9, «Últimos cortes y letra del SVG»): todo
texto de los papeles se mide contra el PDF (`tabla.ancho_mm`), que escribe una etiqueta de
tamaño `size` a `size × 2,45 pt` de em (0,864·size mm) con DejaVu Sans. El SVG escribía
`font-size = size` (em de `size` mm, 16 % más) con Segoe UI (de otra altura de mayúscula). Ahora
el em es el del PDF (`tabla.em_mm`) y la fuente, DejaVu Sans con Verdana de respaldo (Vera, de
la que sale DejaVu, copia sus métricas: misma mayúscula, ancho mediana +1,4 %, p95 +4,9 %)."""

from __future__ import annotations

import base64
from xml.sax.saxutils import escape

from ..library.materials import hatch_pattern
from .esquema import GROSOR_SIMBOLO_MM, LLENO, NEGRO, PILOTAJE, SIMBOLO, trazos_mm
from .sheet import SheetModel
from .tabla import em_mm

_TRAZO, _HUECO = trazos_mm()
#: La fuente del PDF (la de matplotlib) y, donde no esté instalada, la de métricas más cercanas.
FUENTE_SVG = "DejaVu Sans, Verdana, sans-serif"

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
    # trazos de esquema (`esquema.py`): un solo ancho para símbolos y conexiones
    SIMBOLO: f'stroke="{NEGRO}" stroke-width="{GROSOR_SIMBOLO_MM:g}"',
    LLENO: f'stroke="{NEGRO}" stroke-width="{GROSOR_SIMBOLO_MM:g}"',
    PILOTAJE: (f'stroke="{NEGRO}" stroke-width="{GROSOR_SIMBOLO_MM:g}" '
               f'stroke-dasharray="{_TRAZO:g},{_HUECO:g}"'),
}
# círculo y polígono de esquema: sin relleno (símbolo) o negro relleno (punto de unión, flecha)
RELLENO_ESQUEMA = {SIMBOLO: "none", LLENO: NEGRO}
ANCHORS = {"start": "start", "middle": "middle", "end": "end"}


def sheet_to_svg(model: SheetModel) -> str:
    h = model.height

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {model.width} {model.height}" '
        f'width="{model.width}mm" height="{model.height}mm" font-family="{FUENTE_SVG}">',
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
        if poly.kind in RELLENO_ESQUEMA:
            parts.append(
                f'<path d="{d.strip()}" fill="{RELLENO_ESQUEMA[poly.kind]}" {STYLES[poly.kind]} '
                f'stroke-linejoin="round" fill-rule="evenodd"/>'
            )
            continue
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
        if c.kind in RELLENO_ESQUEMA:  # símbolo (sin relleno) o punto de unión (relleno)
            parts.append(
                f'<circle cx="{c.x:.2f}" cy="{h - c.y:.2f}" r="{c.r:.2f}" '
                f'fill="{RELLENO_ESQUEMA[c.kind]}" {STYLES[c.kind]}/>'
            )
        elif c.kind == "corte":  # taladro: trazo de corte, sin relleno
            parts.append(
                f'<circle cx="{c.x:.2f}" cy="{h - c.y:.2f}" r="{c.r:.2f}" '
                f'fill="none" stroke="#c0392b" stroke-width="0.5"/>'
            )
        else:  # globos de BOM / cotas
            parts.append(
                f'<circle cx="{c.x:.2f}" cy="{h - c.y:.2f}" r="{c.r:.2f}" '
                f'fill="#fdfdfb" stroke="#3a5e9c" stroke-width="0.4"/>'
            )
    for a in model.arcs:
        # arco CCW en coords de modelo; el flip h−y preserva la orientación VISUAL
        # → en el sistema y-abajo del SVG el sweep es 0; 3/4 de vuelta → large-arc=1
        import math as _m

        x1 = a.x + a.r * _m.cos(_m.radians(a.a1))
        y1 = h - (a.y + a.r * _m.sin(_m.radians(a.a1)))
        x2 = a.x + a.r * _m.cos(_m.radians(a.a2))
        y2 = h - (a.y + a.r * _m.sin(_m.radians(a.a2)))
        large = 1 if (a.a2 - a.a1) % 360.0 > 180.0 else 0
        parts.append(
            f'<path d="M {x1:.2f} {y1:.2f} A {a.r:.2f} {a.r:.2f} 0 {large} 0 '
            f'{x2:.2f} {y2:.2f}" fill="none" stroke="#16181d" stroke-width="0.25"/>'
        )
    for lab in model.labels:
        x, y = lab.x, h - lab.y
        transform = f' transform="rotate(-{lab.rotation:g} {x:.2f} {y:.2f})"' if lab.rotation else ""
        parts.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="{em_mm(lab.size):.3f}" fill="#16181d" '
            f'text-anchor="{ANCHORS.get(lab.anchor, "middle")}"{transform}>{escape(lab.text)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)
