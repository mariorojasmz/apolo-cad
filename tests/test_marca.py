"""El ícono de Apolo: una fuente (docs/marca/apolo-icono.svg) y sus derivados completos.

Sin Pillow (no es dependencia): los tamaños se leen de las cabeceras PNG e ICO.
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
MARCA = ROOT / "docs" / "marca"
PUBLIC = ROOT / "ui" / "public"


def _png_lado(p: Path) -> tuple[int, int]:
    datos = p.read_bytes()
    assert datos[:8] == b"\x89PNG\r\n\x1a\n", p
    return struct.unpack(">II", datos[16:24])


def _ico_lados(p: Path) -> list[int]:
    datos = p.read_bytes()
    reservado, tipo, n = struct.unpack("<HHH", datos[:6])
    assert (reservado, tipo) == (0, 1), p
    # cada entrada de 16 bytes empieza con ancho, alto (0 = 256)
    return sorted((datos[6 + 16 * i] or 256) for i in range(n))


def test_la_ui_usa_el_svg_maestro():
    assert (PUBLIC / "favicon.svg").read_bytes() == (MARCA / "apolo-icono.svg").read_bytes()


def test_png_de_marca_completos():
    for n in (16, 32, 48, 180, 192, 256, 512):
        assert _png_lado(MARCA / f"apolo-icono-{n}.png") == (n, n)
    assert _png_lado(PUBLIC / "apple-touch-icon.png") == (180, 180)


def test_ico_multitamano():
    assert _ico_lados(MARCA / "apolo-icono.ico") == [16, 32, 48, 256]
    assert _ico_lados(PUBLIC / "favicon.ico") == [16, 32, 48]


def test_index_enlaza_los_iconos():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    for href in ("/favicon.svg", "/favicon.ico", "/apple-touch-icon.png"):
        assert f'href="{href}"' in html, href


def test_el_montaje_de_la_ui_sirve_los_iconos(tmp_path):
    """Igual que `api/main.py`: StaticFiles(html=True) en "/" sirve `public/` copiado a dist."""
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    for nombre in ("favicon.svg", "favicon.ico", "apple-touch-icon.png"):
        shutil.copyfile(PUBLIC / nombre, tmp_path / nombre)
    app = FastAPI()
    app.mount("/", StaticFiles(directory=str(tmp_path), html=True), name="ui")
    cliente = TestClient(app)
    for ruta, tipo in (("/favicon.svg", "image/svg+xml"), ("/favicon.ico", "image/"),
                       ("/apple-touch-icon.png", "image/png")):
        r = cliente.get(ruta)
        assert r.status_code == 200, ruta
        assert r.headers["content-type"].startswith(tipo), (ruta, r.headers["content-type"])
