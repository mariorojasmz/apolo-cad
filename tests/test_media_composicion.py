"""Tarjetas y rótulos del video (`apolo.media.composicion`, plan publicacion-tienda F3, D6).

Sin ffmpeg: todo es Pillow. Lo que se rompe y se vigila aquí:
  - el tamaño (par, el del estilo) y el modo RGB que ffmpeg espera por stdin;
  - el rótulo nunca se sale de su caja, por largo que sea el texto;
  - el fundido: opacidad 0 deja el fotograma intacto;
  - las tildes, eñes y ¿¡: la fuente por defecto de Pillow NO las tiene (medido) y la
    de Apolo sí;
  - la miniatura de YouTube: 1280×720 y menos de 2 MB, también con un render «pesado».
"""

from __future__ import annotations

import random

import pytest

pytest.importorskip("PIL")

from PIL import Image, ImageChops, ImageDraw, ImageFont  # noqa: E402

from apolo.media import composicion as c  # noqa: E402

CHICO = c.Estilo(ancho=640, alto=360)
ESPANOL = "¿Año? ¡Sí! áéíóú ÁÉÍÓÚ ñÑ ü"


def _render(tam=(1000, 780)) -> Image.Image:
    """Un «render» sintético 4:3 con formas, como el de `render_view`."""
    im = Image.new("RGB", tam, (200, 205, 215))
    d = ImageDraw.Draw(im)
    d.rectangle((150, 300, 850, 520), fill=(70, 110, 160))
    d.ellipse((380, 120, 620, 360), fill=(230, 140, 60))
    return im


# ── Estilo y tamaños ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("ancho, alto", [(1921, 1080), (1920, 1081), (0, 1080)])
def test_el_estilo_exige_dimensiones_pares(ancho, alto):
    with pytest.raises(ValueError, match="pares"):
        c.Estilo(ancho=ancho, alto=alto)


def test_cada_tarjeta_sale_rgb_del_tamano_del_estilo():
    tarjetas = [
        c.portada("Transportador de rodillos", "Así se diseñó"),
        c.portada("Transportador de rodillos", "Así se diseñó", fondo=_render()),
    ]
    for im in tarjetas:
        assert im.mode == "RGB"
        assert im.size == (1920, 1080)
    assert c.portada("x", estilo=CHICO).size == (640, 360)


def test_la_portada_recorta_el_fondo_a_cubrir_sin_deformarlo():
    fondo = Image.new("RGB", (400, 300), (0, 200, 0))  # 4:3 → la portada es 16:9
    im = c.portada("Título", fondo=fondo, estilo=CHICO)
    r, g, b = im.getpixel((CHICO.ancho - 2, 2))  # arriba a la derecha: casi sin velo
    assert g > 120 and r < 60 and b < 60, (r, g, b)


# ── Rótulo ────────────────────────────────────────────────────────────────────


TEXTO_LARGO = ("Dos largueros de perfil C unidos por travesaños soldados; las patas se "
               "atornillan para poder desarmarlo y transportarlo en piezas. " * 6)


def test_el_rotulo_envuelve_y_resume_dentro_de_su_caja():
    titulo = "Bastidor, patas y travesaños del transportador de rodillos " * 4
    maqueta = c.maquetar_rotulo(titulo, TEXTO_LARGO)
    titulos = [s for s, *_, es_titulo in maqueta.lineas if es_titulo]
    textos = [s for s, *_, es_titulo in maqueta.lineas if not es_titulo]
    assert len(titulos) == 1 and titulos[0].endswith(c.ELIPSIS)
    assert len(textos) == c.MAX_LINEAS_ROTULO and textos[-1].endswith(c.ELIPSIS)
    x0, y0, x1, y1 = maqueta.caja
    assert 0 < x0 < x1 < c.ESTILO.ancho and 0 < y0 < y1 < c.ESTILO.alto

    # Con los píxeles: sobre un fotograma liso, nada cambia fuera de la caja.
    fondo = Image.new("RGB", (c.ESTILO.ancho, c.ESTILO.alto), (255, 0, 255))
    im = c.rotulo(fondo, titulo, TEXTO_LARGO)
    fuera = Image.new("L", im.size, 255)
    ImageDraw.Draw(fuera).rectangle((x0, y0, x1 - 1, y1 - 1), fill=0)
    diff = ImageChops.difference(im, fondo).convert("L").point(lambda v: 255 if v else 0)
    assert diff.getbbox() is not None
    assert ImageChops.multiply(diff, fuera).getbbox() is None, "el rótulo pinta fuera de su caja"


def test_la_opacidad_hace_el_fundido():
    fot = c._lienzo(c.ESTILO, _render())
    original = fot.tobytes()
    assert c.rotulo(fot, "Rodillos", "Doce rodillos de Ø50", 0.0).tobytes() == original
    lleno = c.rotulo(fot, "Rodillos", "Doce rodillos de Ø50", 1.0)
    medio = c.rotulo(fot, "Rodillos", "Doce rodillos de Ø50", 0.5)
    assert lleno.tobytes() != original
    assert medio.tobytes() not in (original, lleno.tobytes())
    assert fot.tobytes() == original, "el rótulo pintó sobre el fotograma de entrada"


def test_el_rotulo_rechaza_lo_que_no_cuadra():
    with pytest.raises(ValueError, match="mide 640×360"):
        c.rotulo(Image.new("RGB", (640, 360)), "x")
    with pytest.raises(ValueError, match="opacidad"):
        c.rotulo(Image.new("RGB", (1920, 1080)), "x", opacidad=1.5)


def test_un_rotulo_vacio_no_toca_el_fotograma():
    fot = Image.new("RGB", (640, 360), (10, 20, 30))
    assert c.rotulo(fot, "", "", 1.0, CHICO).tobytes() == fot.tobytes()


# ── Texto ─────────────────────────────────────────────────────────────────────


def test_tildes_enes_y_signos_se_dibujan():
    for titulo in (False, True):
        fuente = c.cargar_fuente(c.ESTILO, 40, titulo=titulo)
        assert c.glifos_faltantes(ESPANOL + " … · Ø ° ×", fuente) == []
        assert fuente.getbbox("ñ")[2] > 0


def test_el_detector_caza_la_fuente_de_pillow_sin_tildes():
    """El porqué del default: `load_default` (Aileron recortado) no trae ñ ni tildes."""
    faltan = c.glifos_faltantes(ESPANOL, ImageFont.load_default(size=40))
    assert {"ñ", "á", "¿", "¡"} <= set(faltan)
    assert "A" not in faltan and "?" not in faltan


def test_envolver_parte_palabras_largas_y_respeta_saltos():
    fuente = c.cargar_fuente(c.ESTILO, 30)
    lineas = c.envolver("corta\n" + "x" * 200, fuente, 300)
    assert lineas[0] == "corta" and len(lineas) > 2
    assert all(fuente.getlength(s) <= 300 for s in lineas)
    assert c.envolver("", fuente, 300) == []
    resumido = c.envolver(TEXTO_LARGO, fuente, 300, max_lineas=2)
    assert len(resumido) == 2 and resumido[-1].endswith(c.ELIPSIS)
    assert all(fuente.getlength(s) <= 300 for s in resumido)


def test_una_fuente_explicita_que_no_existe_falla_claro(tmp_path):
    estilo = c.Estilo(fuente=str(tmp_path / "no-esta.ttf"))
    with pytest.raises(FileNotFoundError, match="no-esta.ttf"):
        c.portada("x", estilo=estilo)


def test_la_fuente_explicita_se_usa():
    estilo = c.Estilo(fuente=c.ruta_fuente_por_defecto(negrita=True))
    assert c.cargar_fuente(estilo, 30).getname()[1] == "Bold"
    assert c.cargar_fuente(c.ESTILO, 30).getname()[1] == "Book"


# ── Miniatura ─────────────────────────────────────────────────────────────────


def test_miniatura_1280x720_y_menos_de_2mb(tmp_path):
    im = c.miniatura(_render(), "Transportador de rodillos: así se diseñó")
    assert im.size == c.TAM_MINIATURA and im.mode == "RGB"
    ruta = c.guardar_miniatura(im, tmp_path / "miniatura.png")
    assert ruta.suffix == ".png" and ruta.stat().st_size < c.LIMITE_MINIATURA
    assert Image.open(ruta).size == (1280, 720)


def test_una_miniatura_pesada_cae_a_jpeg(tmp_path):
    """Ruido puro: el PNG pasa de 2 MB (YouTube lo rechaza) → JPEG que sí entra."""
    rnd = random.Random(7)
    ruido = Image.frombytes("RGB", c.TAM_MINIATURA,
                            rnd.randbytes(1280 * 720 * 3))
    ruta = c.guardar_miniatura(ruido, tmp_path / "miniatura.png")
    assert ruta.suffix == ".jpg" and ruta.stat().st_size < c.LIMITE_MINIATURA
    assert not (tmp_path / "miniatura.png").exists()


def test_guardar_miniatura_rechaza_otro_tamano(tmp_path):
    with pytest.raises(ValueError, match="1280×720"):
        c.guardar_miniatura(Image.new("RGB", (1920, 1080)), tmp_path / "m.png")
