"""Portada, rótulos y miniatura del video, dibujados con Pillow (plan publicacion-tienda, D6).
El cierre (la portada de la tienda, D10 de fabrica-de-publicaciones) está en `cierre.py`.

Funciones puras: reciben textos e imágenes y devuelven una `PIL.Image` RGB del tamaño del
`Estilo` (la miniatura, 1280×720). No conocen el documento ni el render: el fotograma les
llega hecho.

Fuente: `ImageFont.load_default(size)` NO sirve en español. En Pillow 12.3 es un subconjunto
de Aileron sin tildes, eñes ni ¿¡ (medido con `glifos_faltantes`: «ñ», «á», «¿» salen como
su caja .notdef). El default es DejaVu Sans, la que ya trae matplotlib (dependencia dura de
apolo-cad; licencia Bitstream Vera, libre): la misma en Windows, Linux y macOS, que es lo que
D6 buscaba al descartar `drawtext`. `Estilo.fuente` acepta otra TTF/OTF.
"""

from __future__ import annotations

import importlib.util
import warnings
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError as exc:  # pragma: no cover - Pillow llega con matplotlib (dependencia dura)
    raise ImportError("La composición del video necesita Pillow: `pip install pillow`") from exc

Color = tuple[int, int, int]

#: Miniatura de YouTube: 1280×720 y menos de 2 MB (D15). 2 MB decimales: el más estricto.
TAM_MINIATURA = (1280, 720)
LIMITE_MINIATURA = 2_000_000
MAX_LINEAS_ROTULO = 3
#: La marca de la miniatura. El cierre (la portada de la tienda) vive en `cierre.py`.
MARCA = "Apolo CAD"
ELIPSIS = "…"
#: Los tamaños del `Estilo` son px para un lado corto de 1080; se escalan con el real.
_REF = 1080
#: Uso privado del plano 16: ninguna fuente lo dibuja, así que sale su .notdef.
_SIN_GLIFO = "\U0010fffd"


@dataclass(frozen=True)
class Estilo:
    """Cómo se ve el video. Colores de la UI (`ui/src/styles.css`); tamaños en px a 1080."""

    ancho: int = 1920
    alto: int = 1080
    color_fondo: Color = (18, 20, 25)
    color_panel: Color = (30, 34, 43)
    color_texto: Color = (223, 228, 236)
    color_secundario: Color = (139, 147, 163)
    color_acento: Color = (91, 140, 255)
    opacidad_panel: float = 0.82
    margen: int = 72
    tam_titulo: int = 84
    tam_texto: int = 38
    fuente: str | None = None
    fuente_titulos: str | None = None

    def __post_init__(self):
        if self.ancho <= 0 or self.alto <= 0 or self.ancho % 2 or self.alto % 2:
            raise ValueError(
                f"El video H.264 (yuv420p) necesita ancho y alto pares: {self.ancho}×{self.alto}")
        if not 0 <= self.opacidad_panel <= 1:
            raise ValueError(f"opacidad_panel va de 0 a 1: {self.opacidad_panel}")

    def px(self, valor: float) -> int:
        """`valor` (px a 1080) escalado al lado corto de este estilo."""
        return max(1, round(valor * min(self.ancho, self.alto) / _REF))


ESTILO = Estilo()


# ── Fuentes ───────────────────────────────────────────────────────────────────


@lru_cache(maxsize=2)
def ruta_fuente_por_defecto(negrita: bool = False) -> str | None:
    """DejaVu Sans de matplotlib, ubicada sin importar matplotlib (sólo su carpeta)."""
    spec = importlib.util.find_spec("matplotlib")
    nombre = "DejaVuSans-Bold.ttf" if negrita else "DejaVuSans.ttf"
    for base in (spec.submodule_search_locations or []) if spec else []:
        ruta = Path(base) / "mpl-data" / "fonts" / "ttf" / nombre
        if ruta.is_file():
            return str(ruta)
    return None


@lru_cache(maxsize=64)
def _cargar(ruta: str | None, tam: int):
    if ruta is None:
        warnings.warn("No encuentro DejaVu Sans (viene con matplotlib): uso la fuente de Pillow, "
                      "que dibuja las tildes y las eñes como cajas. Pasa una TTF en "
                      "`Estilo.fuente`.", RuntimeWarning, stacklevel=3)
        return ImageFont.load_default(size=tam)
    return ImageFont.truetype(ruta, tam)


def cargar_fuente(estilo: Estilo, tam: int, *, titulo: bool = False):
    """La fuente del estilo a `tam` px: la TTF explícita o DejaVu Sans (negrita en títulos)."""
    explicita = (estilo.fuente_titulos if titulo else None) or estilo.fuente
    if explicita:
        if not Path(explicita).is_file():
            raise FileNotFoundError(
                f"No encuentro la fuente «{explicita}»: pasa la ruta de un .ttf u .otf que exista.")
        return _cargar(str(explicita), tam)
    return _cargar(ruta_fuente_por_defecto(negrita=titulo), tam)


def _mascara(fuente, caracter: str) -> bytes:
    tam = int(getattr(fuente, "size", 40))
    im = Image.new("L", (tam * 3, tam * 3), 0)
    ImageDraw.Draw(im).text((tam, tam), caracter, font=fuente, fill=255)
    return im.tobytes()


def glifos_faltantes(texto: str, fuente) -> list[str]:
    """Los caracteres de `texto` que `fuente` no tiene (los dibujaría como su caja .notdef)."""
    caja = _mascara(fuente, _SIN_GLIFO)
    return [c for c in dict.fromkeys(texto) if not c.isspace() and _mascara(fuente, c) == caja]


# ── Texto en un ancho ─────────────────────────────────────────────────────────


def _con_elipsis(texto: str, fuente, ancho_max: float) -> str:
    texto = texto.rstrip()
    while texto and fuente.getlength(texto + ELIPSIS) > ancho_max:
        texto = texto[:-1].rstrip()
    if texto or fuente.getlength(ELIPSIS) <= ancho_max:
        return texto + ELIPSIS
    return ""


def elidir(texto: str, fuente, ancho_max: float) -> str:
    """`texto` tal cual si cabe en `ancho_max` px; si no, recortado con «…»."""
    return texto if fuente.getlength(texto) <= ancho_max else _con_elipsis(texto, fuente, ancho_max)


def _partir_palabra(palabra: str, fuente, ancho_max: float) -> list[str]:
    trozos, actual = [], ""
    for c in palabra:
        if actual and fuente.getlength(actual + c) > ancho_max:
            trozos.append(actual)
            actual = c
        else:
            actual += c
    return trozos + [actual]


def envolver(texto: str, fuente, ancho_max: float, max_lineas: int | None = None) -> list[str]:
    """`texto` en líneas que caben en `ancho_max` px, por palabras.

    Una palabra más ancha que la línea se parte por caracteres; los saltos de línea del
    texto se respetan. Con `max_lineas`, lo que sobra se resume con «…» en la última.
    """
    lineas: list[str] = []
    for parrafo in texto.split("\n"):
        actual = ""
        for palabra in parrafo.split():
            prueba = f"{actual} {palabra}" if actual else palabra
            if fuente.getlength(prueba) <= ancho_max:
                actual = prueba
                continue
            if actual:
                lineas.append(actual)
            *llenas, actual = _partir_palabra(palabra, fuente, ancho_max)
            lineas += llenas
        lineas.append(actual)
    while lineas and not lineas[-1]:
        lineas.pop()
    if max_lineas is not None and len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        lineas[-1] = _con_elipsis(lineas[-1], fuente, ancho_max)
    return lineas


def _alto_linea(fuente, interlineado: float = 1.15) -> int:
    ascenso, descenso = fuente.getmetrics()
    return round((ascenso + descenso) * interlineado)


def _una_linea(texto: str, estilo: Estilo, tam: int, minimo: int, ancho_max: float, *,
               titulo: bool = False):
    """(texto, fuente) en UNA línea: achica la letra hasta `minimo` y, si aún no cabe, elide."""
    for t in range(tam, minimo - 1, -max(1, tam // 12)):
        fuente = cargar_fuente(estilo, t, titulo=titulo)
        if fuente.getlength(texto) <= ancho_max:
            return texto, fuente
    fuente = cargar_fuente(estilo, minimo, titulo=titulo)
    return elidir(texto, fuente, ancho_max), fuente


# ── Lienzos ───────────────────────────────────────────────────────────────────


def _degradado(tam: tuple[int, int], arriba: float, abajo: float) -> Image.Image:
    """Máscara L vertical: `arriba` en la fila 0 y `abajo` en la última (0..1)."""
    rampa = Image.linear_gradient("L").resize(tam)
    return rampa.point(lambda v: round(255 * (arriba + (abajo - arriba) * v / 255)))


def _lienzo(estilo: Estilo, fondo: Image.Image | None = None) -> Image.Image:
    """Fondo de una tarjeta: el render recortado a cubrir y velado abajo, o un degradado."""
    tam = (estilo.ancho, estilo.alto)
    if fondo is None:
        return Image.composite(Image.new("RGB", tam, estilo.color_panel),
                               Image.new("RGB", tam, estilo.color_fondo),
                               _degradado(tam, 0.0, 0.6))
    base = ImageOps.fit(fondo.convert("RGB"), tam, Image.Resampling.LANCZOS)
    velo = Image.new("RGB", tam, estilo.color_fondo)
    return Image.composite(velo, base, _degradado(tam, 0.25, 0.9))


def _bloque(draw, items: list, x: float, y: float, *, centrado: bool = False) -> float:
    """Dibuja `items` = (texto, fuente, color) | separación en px, de arriba abajo."""
    for item in items:
        if isinstance(item, int):
            y += item
            continue
        texto, fuente, color = item
        draw.text((x, y), texto, font=fuente, fill=color, anchor="ma" if centrado else "la")
        y += _alto_linea(fuente)
    return y


def _alto_bloque(items: list) -> int:
    return sum(it if isinstance(it, int) else _alto_linea(it[1]) for it in items)


# ── Portada y miniatura ───────────────────────────────────────────────────────


def _ancho_portada(estilo: Estilo) -> float:
    return (estilo.ancho - 2 * estilo.px(estilo.margen)) * (0.8 if estilo.ancho > estilo.alto
                                                             else 1.0)


def _portada(titulo: str, subtitulo: str, fondo, estilo: Estilo, escala: float) -> Image.Image:
    im = _lienzo(estilo, fondo)
    draw = ImageDraw.Draw(im)
    m = estilo.px(estilo.margen)
    ancho_texto = _ancho_portada(estilo)
    f_tit = cargar_fuente(estilo, estilo.px(estilo.tam_titulo * escala), titulo=True)
    f_sub = cargar_fuente(estilo, estilo.px(estilo.tam_texto * 1.2))
    barra = estilo.px(10)
    items: list = [barra * 3]
    items += [(s, f_tit, estilo.color_texto) for s in envolver(titulo, f_tit, ancho_texto, 3)]
    sub = envolver(subtitulo, f_sub, ancho_texto, 2)
    if sub:
        items += [estilo.px(16)] + [(s, f_sub, estilo.color_secundario) for s in sub]
    alto = _alto_bloque(items)
    y = estilo.alto - 2 * m - alto if fondo is not None else (estilo.alto - alto) / 2
    draw.rectangle((m, y, m + estilo.px(140), y + barra - 1), fill=estilo.color_acento)
    _bloque(draw, items, m, y)
    return im


def portada(titulo: str, subtitulo: str = "", fondo: Image.Image | None = None,
            estilo: Estilo = ESTILO) -> Image.Image:
    """Tarjeta de título. Con `fondo` (un render), lo recorta a cubrir sin deformarlo, lo
    vela abajo para que el texto se lea y apoya el título abajo a la izquierda; sin fondo,
    el título va centrado en vertical sobre un degradado."""
    return _portada(titulo, subtitulo, fondo, estilo, 1.0)


ESCALAS_MINIATURA = (1.45, 1.3, 1.15, 1.0, 0.9, 0.8, 0.7, 0.6)


def maquetar_miniatura(titulo: str, estilo: Estilo = ESTILO) -> tuple[float, list[str]]:
    """(escala, líneas) del título en la miniatura: la letra más grande con la que entra ENTERO
    (sin «…», palabras partidas ni una última línea de 1-3 letras, «2 / m») en 2 líneas; si no,
    en 3 con letra de 1.0 para abajo. Más de 100 caracteres se cortan en la más chica."""
    est = replace(estilo, ancho=TAM_MINIATURA[0], alto=TAM_MINIATURA[1])
    palabras = titulo.split()
    for maximo, escalas in ((2, ESCALAS_MINIATURA), (3, [e for e in ESCALAS_MINIATURA if e <= 1])):
        for escala in escalas:
            f = cargar_fuente(est, est.px(est.tam_titulo * escala), titulo=True)
            lineas = envolver(titulo, f, _ancho_portada(est))
            if (len(lineas) <= maximo and " ".join(lineas).split() == palabras
                    and (len(lineas) == 1 or len(lineas[-1]) > 3)):
                return escala, lineas
    return escala, envolver(titulo, f, _ancho_portada(est), 3)


def miniatura(render: Image.Image | None, titulo: str, estilo: Estilo = ESTILO,
              marca: str = MARCA) -> Image.Image:
    """Miniatura de YouTube y póster de la tienda (1280×720, D15): el render, el título legible
    lo más grande que entre entero (`maquetar_miniatura`) y la marca debajo."""
    ancho, alto = TAM_MINIATURA
    escala, _ = maquetar_miniatura(titulo, estilo)
    return _portada(titulo, marca, render, replace(estilo, ancho=ancho, alto=alto), escala)


def guardar_miniatura(imagen: Image.Image, ruta, limite: int = LIMITE_MINIATURA) -> Path:
    """Guarda la miniatura en PNG si pesa menos de `limite`; si no, en JPEG (`.jpg` al lado,
    sin dejar el PNG) bajando la calidad hasta que entre. Devuelve la ruta escrita."""
    ruta = Path(ruta)
    if ruta.suffix.lower() != ".png":
        raise ValueError(f"La miniatura se pide en .png (cae a .jpg sólo si pesa): {ruta.name}")
    if imagen.size != TAM_MINIATURA:
        raise ValueError(f"La miniatura mide {imagen.size[0]}×{imagen.size[1]} y YouTube pide "
                         f"{TAM_MINIATURA[0]}×{TAM_MINIATURA[1]}")
    rgb = imagen.convert("RGB")
    rgb.save(ruta, format="PNG", optimize=True)
    if ruta.stat().st_size < limite:
        return ruta
    ruta.unlink()
    jpg = ruta.with_suffix(".jpg")
    for calidad in (92, 85, 78, 70, 60, 50):
        rgb.save(jpg, format="JPEG", quality=calidad, optimize=True, progressive=True)
        if jpg.stat().st_size < limite:
            return jpg
    jpg.unlink()
    raise ValueError(f"La miniatura no baja de {limite} bytes ni en JPEG de calidad 50")


# ── Rótulo inferior ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MaquetaRotulo:
    """Dónde va cada cosa del rótulo: `caja` = (x0, y0, x1, y1) del panel y `lineas` =
    (texto, x, y, es_titulo). Ninguna línea sale de la caja ni la caja del fotograma."""

    caja: tuple[int, int, int, int]
    barra: int
    lineas: list[tuple[str, int, int, bool]]


def maquetar_rotulo(titulo: str, texto: str = "", estilo: Estilo = ESTILO) -> MaquetaRotulo:
    """El rótulo inferior: título en una línea y texto en hasta 3, con «…» si no cabe."""
    m = estilo.px(estilo.margen)
    ancho_panel = estilo.ancho - 2 * m
    if estilo.ancho > estilo.alto:
        ancho_panel = min(ancho_panel, round(estilo.ancho * 0.62))
    pad, barra = estilo.px(28), estilo.px(8)
    ancho_texto = ancho_panel - barra - 2 * pad
    f_tit, f_txt = _fuentes_rotulo(estilo)
    tit = envolver(titulo, f_tit, ancho_texto, 1)
    txt = envolver(texto, f_txt, ancho_texto, MAX_LINEAS_ROTULO)
    alto_tit, alto_txt = _alto_linea(f_tit), _alto_linea(f_txt)
    gap = estilo.px(10) if tit and txt else 0
    alto = 2 * pad + alto_tit * len(tit) + gap + alto_txt * len(txt)
    x0, y1 = m, estilo.alto - m
    y0 = y1 - alto
    tx, y = x0 + barra + pad, y0 + pad
    lineas = []
    for s in tit:
        lineas.append((s, tx, y, True))
        y += alto_tit
    y += gap
    for s in txt:
        lineas.append((s, tx, y, False))
        y += alto_txt
    return MaquetaRotulo((x0, y0, x0 + ancho_panel, y1), barra, lineas)


def _fuentes_rotulo(estilo: Estilo):
    return (cargar_fuente(estilo, estilo.px(estilo.tam_texto * 1.25), titulo=True),
            cargar_fuente(estilo, estilo.px(estilo.tam_texto)))


def rotulo(fotograma: Image.Image, titulo: str, texto: str = "", opacidad: float = 1.0,
           estilo: Estilo = ESTILO) -> Image.Image:
    """El rótulo inferior sobre `fotograma`. `opacidad` (0..1) hace el fundido de entrada y
    de salida: con 0 devuelve el fotograma intacto."""
    if fotograma.size != (estilo.ancho, estilo.alto):
        raise ValueError(f"El fotograma mide {fotograma.size[0]}×{fotograma.size[1]} y el "
                         f"estilo {estilo.ancho}×{estilo.alto}")
    if not 0 <= opacidad <= 1:
        raise ValueError(f"La opacidad del rótulo va de 0 a 1: {opacidad}")
    base = fotograma.convert("RGB")  # siempre una copia: el fotograma de entrada no se toca
    maqueta = maquetar_rotulo(titulo, texto, estilo)
    if opacidad == 0 or not maqueta.lineas:
        return base
    # Sólo se compone la caja: a 1080p, 11 ms por fotograma contra 21 con la capa entera.
    x0, y0 = maqueta.caja[:2]
    capa = _panel_rotulo(maqueta, estilo, estilo.opacidad_panel)
    if opacidad < 1:
        capa.putalpha(capa.getchannel("A").point(lambda a: round(a * opacidad)))
    zona = Image.alpha_composite(base.crop(maqueta.caja).convert("RGBA"), capa)
    base.paste(zona.convert("RGB"), (x0, y0))
    return base


def _panel_rotulo(maqueta: MaquetaRotulo, estilo: Estilo, opacidad_panel: float) -> Image.Image:
    """El panel del rótulo (RGBA del tamaño de su caja): fondo, barra de acento y líneas."""
    x0, y0, x1, y1 = maqueta.caja
    capa = Image.new("RGBA", (x1 - x0, y1 - y0),
                     (*estilo.color_panel, round(255 * opacidad_panel)))
    draw = ImageDraw.Draw(capa)
    draw.rectangle((0, 0, maqueta.barra - 1, y1 - y0 - 1), fill=(*estilo.color_acento, 255))
    f_tit, f_txt = _fuentes_rotulo(estilo)
    for s, x, y, es_titulo in maqueta.lineas:
        color = estilo.color_texto if es_titulo else estilo.color_secundario
        draw.text((x - x0, y - y0), s, font=f_tit if es_titulo else f_txt, fill=(*color, 255),
                  anchor="la")
    return capa


def opacidad_rotulo_legible(estilo: Estilo = ESTILO) -> float:
    """La opacidad del panel con la que el título y el texto del rótulo se leen a ≥ 4.5:1 sobre
    CUALQUIER cuadro (D4 de video-montaje-pulido): nunca menos que la del estilo."""
    from .contraste import opacidad_legible

    return opacidad_legible((estilo.color_texto, estilo.color_secundario), estilo.color_panel,
                            minima=estilo.opacidad_panel)


def capa_rotulo(titulo: str, texto: str = "", estilo: Estilo = ESTILO) -> Image.Image:
    """El rótulo inferior como capa RGBA del tamaño del cuadro (transparente fuera del panel),
    para que otro lo dibuje encima con su fundido: el navegador del video-realista (D5). El
    panel va con `opacidad_rotulo_legible`: el contraste no depende de lo que haya detrás."""
    capa = Image.new("RGBA", (estilo.ancho, estilo.alto), (0, 0, 0, 0))
    maqueta = maquetar_rotulo(titulo, texto, estilo)
    if maqueta.lineas:
        capa.paste(_panel_rotulo(maqueta, estilo, opacidad_rotulo_legible(estilo)),
                   maqueta.caja[:2])
    return capa
