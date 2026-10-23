"""El cierre del video es la portada de la tienda y las cifras salen del video (D10 de
fabrica-de-publicaciones, ajuste de Mario tras ver el primer video real).

`media/cierre.py`: logo, lema con su subrayado, dominio y aviso, sin cortes en 1920×1080 ni en
1280×720. La línea de tiempo (VTK y navegador) ya no tiene la parte «cifras», aunque el guion
de antes le dé segundos; el guion las sigue llevando (de ahí salen las de `ficha.json`).
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("PIL")

from apolo.media import cierre as c  # noqa: E402
from apolo.media import composicion as comp  # noqa: E402
from apolo.media import tarjetas  # noqa: E402
from apolo.services import guion_video as gv  # noqa: E402
from apolo.services import linea_tiempo as lt  # noqa: E402

MAESTRO = Path(__file__).resolve().parents[1] / "docs" / "marca" / "apolo-icono.svg"
TAMANOS = [(1920, 1080), (1280, 720)]


def _guion_viejo() -> dict:
    """Un guion de antes de D10: cifras de 6 s y el cierre «Descarga los planos…»."""
    etapas = [{"titulo": t, "texto": "", "pasos": [i + 1], "duracion_s": 12.0}
              for i, t in enumerate(["Bastidor", "Rodillos", "Transmisión"])]
    return {"version": 1, "idioma": "es", "documento": {"nombre": "x", "comandos": 9, "firma": "f"},
            "titulo": "T", "subtitulo": "", "video": {"ancho": 320, "alto": 180, "fps": 30},
            "portada": {"duracion_s": 4.0}, "etapas": etapas,
            "cifras": {"titulo": "En cifras", "items": [{"etiqueta": "Piezas", "valor": "9"}],
                       "duracion_s": 6.0},
            "orbita": {"duracion_s": 8.0},
            "cierre": {"texto": "Descarga los planos y el modelo 3D",
                       "url": "https://apolocad.com/maquinas/faja", "duracion_s": 5.0}}


# ── Textos ────────────────────────────────────────────────────────────────────


def test_el_lema_y_el_dominio_salen_del_guion_con_sus_respaldos():
    g = _guion_viejo()
    assert c.textos_cierre(g, {}) == ("Máquinas listas para fabricar", "apolocad.com")
    assert c.textos_cierre(g, {c.LEMA_ENV: "Planos que se fabrican"})[0] == "Planos que se fabrican"
    g["cierre"].update(texto="Otro lema", url="https://www.tienda.example/maquinas/x?y=1")
    assert c.textos_cierre(g, {}) == ("Otro lema", "tienda.example")
    g["cierre"].update(texto="", url="")
    assert c.textos_cierre(g, {c.URL_ENV: "https://staging.apolocad.com"}) == (
        c.LEMA, "staging.apolocad.com")
    assert c.textos_cierre(g, {})[1] == c.DOMINIO


def test_el_lema_del_guion_nuevo_es_el_de_la_tienda():
    assert gv.CIERRE == c.LEMA and gv.LEMA_ENV == c.LEMA_ENV  # copias: services no importa media


# ── Maqueta: nada se corta ni se pisa ─────────────────────────────────────────


def _dentro(caja, ancho, alto) -> bool:
    x0, y0, x1, y1 = caja
    return 0 <= x0 < x1 <= ancho and 0 <= y0 < y1 <= alto


def _se_pisan(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@pytest.mark.parametrize("ancho, alto", TAMANOS)
@pytest.mark.parametrize("lema, dominio", [
    (c.LEMA, c.DOMINIO),
    ("Transportadores, mesas y estructuras de taller listas para fabricar hoy mismo",
     "tienda-de-maquinas-industriales.example.com"),
])
def test_el_cierre_entra_entero(ancho, alto, lema, dominio):
    est = replace(comp.ESTILO, ancho=ancho, alto=alto)
    mq = c.maquetar_cierre(lema, dominio, est)
    lineas = [s for s, _, _ in mq.lema]
    assert 2 <= len(lineas) <= 3 and " ".join(lineas).split() == lema.split()
    assert mq.dominio[0] == dominio and mq.aviso and comp.ELIPSIS not in "".join(
        s for s, _, _ in mq.aviso)
    assert " ".join(s for s, _, _ in mq.aviso) == c.AVISO_CIERRE
    cajas = [mq.logo, *mq.cajas_lema, mq.subrayado, mq.caja_dominio, *mq.cajas_aviso]
    m = est.px(est.margen) // 2
    assert all(_dentro(k, ancho, alto) for k in cajas), cajas
    assert all(k[0] >= m and k[2] <= ancho - m for k in cajas)
    # de arriba abajo: logo, lema, subrayado, dominio, aviso; sin pisarse (el subrayado va
    # bajo la última línea y puede cruzar sus descendentes, como en la tienda)
    orden = [mq.logo, mq.cajas_lema[0], mq.subrayado, mq.caja_dominio, mq.cajas_aviso[0]]
    assert all(a[1] < b[1] for a, b in zip(orden, orden[1:]))
    sin_sub = [mq.logo, *mq.cajas_lema, mq.caja_dominio, *mq.cajas_aviso]
    assert not any(_se_pisan(a, b) for i, a in enumerate(sin_sub) for b in sin_sub[i + 1:])
    assert not _se_pisan(mq.subrayado, mq.caja_dominio)


def test_el_lema_corto_va_grande_en_dos_lineas_parejas():
    mq = c.maquetar_cierre()
    assert [s for s, _, _ in mq.lema] == ["Máquinas listas", "para fabricar"]
    assert mq.tam_lema == comp.ESTILO.px(124)
    ultima = mq.cajas_lema[-1]
    ancho = ultima[2] - ultima[0]
    # el subrayado sobresale ~2 % por lado de la última línea, como el de la tienda
    assert mq.subrayado[0] < ultima[0] and mq.subrayado[2] > ultima[2]
    assert mq.subrayado[2] - mq.subrayado[0] == pytest.approx(ancho * 1.04, abs=3)
    assert mq.subrayado[1] > ultima[1]


# ── Dibujo ────────────────────────────────────────────────────────────────────


def _cuenta(im, color, tol=30) -> int:
    r0, g0, b0 = color
    return sum(1 for r, g, b in im.getdata()
               if abs(r - r0) < tol and abs(g - g0) < tol and abs(b - b0) < tol)


@pytest.mark.parametrize("ancho, alto", TAMANOS)
def test_el_cierre_dibuja_la_portada_de_la_tienda(ancho, alto):
    est = replace(comp.ESTILO, ancho=ancho, alto=alto)
    im = c.cierre(estilo=est)
    assert im.mode == "RGB" and im.size == (ancho, alto)
    mq = c.maquetar_cierre(estilo=est)
    assert im.getpixel((2, 2)) == c.FONDO  # la tinta oscura del hero
    assert _cuenta(im.crop(mq.caja_dominio), c.AMBAR) > 200  # el dominio en ámbar
    assert _cuenta(im.crop(mq.subrayado), c.ACENTO) > 200  # el subrayado azul
    assert _cuenta(im.crop(mq.logo), c.AZUL_MARCA) > 0.4 * (mq.logo[2] - mq.logo[0]) ** 2
    assert _cuenta(im.crop(mq.cajas_lema[0]), c.BLANCO) > 500


def test_la_a_es_la_del_maestro_de_la_marca():
    raiz = ET.parse(MAESTRO).getroot()
    ns = "{http://www.w3.org/2000/svg}"
    rect, trazo, linea = raiz.find(f"{ns}rect"), raiz.find(f"{ns}path"), raiz.find(f"{ns}line")
    assert float(raiz.attrib["viewBox"].split()[2]) == c.ICONO_LADO
    assert float(rect.attrib["rx"]) == c.ICONO_RADIO
    assert rect.attrib["fill"].lower() == "#%02x%02x%02x" % c.AZUL_MARCA
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", trazo.attrib["d"])]
    assert list(zip(nums[0::2], nums[1::2])) == c.ICONO_A[0]
    assert float(trazo.attrib["stroke-width"]) == c.ICONO_A[1]
    assert [(float(linea.attrib[f"x{i}"]), float(linea.attrib[f"y{i}"])) for i in (1, 2)] == \
        c.ICONO_TRAVESANO[0]
    assert float(linea.attrib["stroke-width"]) == c.ICONO_TRAVESANO[1]
    assert linea.attrib["stroke"].lower() == "#%02x%02x%02x" % c.AMBAR
    assert c.logo(64).size == (64, 64)


# ── Los dos caminos: el cierre nuevo y sin cifras ─────────────────────────────


def test_la_tarjeta_de_cifras_ya_no_existe():
    assert "cifras" not in tarjetas.PARTES
    with pytest.raises(tarjetas.TarjetaError, match="no existe"):
        tarjetas.tarjeta(_guion_viejo(), "cifras", 320, 180)
    assert not hasattr(comp, "tarjeta_cifras")


def test_un_guion_viejo_con_cifras_sigue_valiendo_y_no_las_muestra():
    g = _guion_viejo()
    gv.validar_guion(g)
    partes = [t.parte for t in lt.tramos(g)]
    assert partes == ["portada", "etapa", "etapa", "etapa", "orbita", "cierre"]
    assert gv.duracion_total(g) == 4 + 36 + 8 + 5  # los 6 s de cifras no cuentan
    assert lt.total_fotogramas(lt.tramos(g)) == round(gv.duracion_total(g) * 30)
    sin = copy.deepcopy(g)
    sin["cifras"].update(items=[], duracion_s=3.0)  # antes era un error; ahora se ignora
    gv.validar_guion(sin)


def test_los_capitulos_terminan_en_la_maquina_terminada():
    caps = gv.capitulos(_guion_viejo())
    assert len(caps) >= 3 and caps[-1][1] == gv.TITULO_FINAL
    assert all(t != gv.TITULO_CIFRAS for _, t in caps)
