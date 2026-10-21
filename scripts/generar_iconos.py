"""Genera los PNG y el ICO del ícono de Apolo desde el SVG maestro.

    .venv\\Scripts\\python.exe scripts\\generar_iconos.py

Fuente única: `docs/marca/apolo-icono.svg` (la A de taller). El script LEE su geometría
(cuadrado redondeado, la A abierta y el travesaño) y la dibuja a 1024 px con Pillow; cada
tamaño sale de reducir ese dibujo con LANCZOS. Escribe:

- `docs/marca/apolo-icono-<n>.png` para n = 16, 32, 48, 180, 192, 256, 512;
- `docs/marca/apolo-icono.ico` (16/32/48/256, para el instalador de Windows);
- `ui/public/favicon.svg` (copia del maestro), `ui/public/favicon.ico` (16/32/48) y
  `ui/public/apple-touch-icon.png` (180).

Pillow es herramienta de desarrollo, NO dependencia del paquete: si falta, instálala en el
venv (`pip install pillow`) sólo para correr este script.
"""

from __future__ import annotations

import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARCA = ROOT / "docs" / "marca"
MAESTRO = MARCA / "apolo-icono.svg"
PUBLIC = ROOT / "ui" / "public"

TAMANOS_PNG = (16, 32, 48, 180, 192, 256, 512)
TAMANOS_ICO = (16, 32, 48, 256)
TAMANOS_FAVICON = (16, 32, 48)
LIENZO = 1024  # px del dibujo de alta resolución

_NS = "{http://www.w3.org/2000/svg}"
Punto = tuple[float, float]


def leer_maestro(svg: Path = MAESTRO) -> dict:
    """Geometría del SVG maestro, en unidades de su viewBox."""
    raiz = ET.parse(svg).getroot()
    _, _, ancho, alto = (float(v) for v in raiz.attrib["viewBox"].split())
    if ancho != alto:
        raise ValueError(f"el ícono debe ser cuadrado: viewBox {ancho}×{alto}")
    rect = raiz.find(f"{_NS}rect")
    trazo = raiz.find(f"{_NS}path")
    linea = raiz.find(f"{_NS}line")
    if rect is None or trazo is None or linea is None:
        raise ValueError("el maestro debe tener un rect, un path (la A) y una line (travesaño)")
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", trazo.attrib["d"])]
    puntos = list(zip(nums[0::2], nums[1::2]))
    return {
        "lado": ancho,
        "fondo": (float(rect.attrib.get("rx", 0)), rect.attrib["fill"]),
        "a": (puntos, float(trazo.attrib["stroke-width"]), trazo.attrib["stroke"]),
        "travesano": (
            [(float(linea.attrib["x1"]), float(linea.attrib["y1"])),
             (float(linea.attrib["x2"]), float(linea.attrib["y2"]))],
            float(linea.attrib["stroke-width"]),
            linea.attrib["stroke"],
        ),
    }


def _trazo_redondeado(draw, puntos: list[Punto], ancho: float, color: str) -> None:
    """Polilínea con puntas y uniones redondeadas (stroke-linecap/linejoin="round")."""
    r = ancho / 2
    for (x0, y0), (x1, y1) in zip(puntos, puntos[1:]):
        dx, dy = x1 - x0, y1 - y0
        largo = (dx * dx + dy * dy) ** 0.5
        nx, ny = -dy / largo * r, dx / largo * r
        draw.polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                      (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], fill=color)
    for x, y in puntos:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def dibujar(geo: dict, lienzo: int = LIENZO):
    """El ícono a `lienzo` px, RGBA (las esquinas fuera del redondeo son transparentes)."""
    from PIL import Image, ImageDraw

    k = lienzo / geo["lado"]
    img = Image.new("RGBA", (lienzo, lienzo), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    rx, fondo = geo["fondo"]
    draw.rounded_rectangle([0, 0, lienzo - 1, lienzo - 1], radius=rx * k, fill=fondo)
    for puntos, ancho, color in (geo["a"], geo["travesano"]):
        _trazo_redondeado(draw, [(x * k, y * k) for x, y in puntos], ancho * k, color)
    return img


def reducir(img, n: int):
    from PIL import Image

    return img.resize((n, n), Image.Resampling.LANCZOS)


def guardar_ico(img, destino: Path, tamanos: tuple[int, ...]) -> None:
    """ICO multi-tamaño con cada cuadro reducido por LANCZOS (no el resize interno del ICO)."""
    cuadros = [reducir(img, n) for n in sorted(tamanos, reverse=True)]
    cuadros[0].save(destino, format="ICO", sizes=[(n, n) for n in sorted(tamanos)],
                    append_images=cuadros[1:])


def main() -> int:
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Falta Pillow en este Python: pip install pillow (sólo para este script).",
              file=sys.stderr)
        return 1

    img = dibujar(leer_maestro())
    MARCA.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    for n in TAMANOS_PNG:
        reducir(img, n).save(MARCA / f"apolo-icono-{n}.png", optimize=True)
    guardar_ico(img, MARCA / "apolo-icono.ico", TAMANOS_ICO)

    shutil.copyfile(MAESTRO, PUBLIC / "favicon.svg")
    guardar_ico(img, PUBLIC / "favicon.ico", TAMANOS_FAVICON)
    reducir(img, 180).save(PUBLIC / "apple-touch-icon.png", optimize=True)

    print(f"Íconos generados en {MARCA.relative_to(ROOT)} y {PUBLIC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
