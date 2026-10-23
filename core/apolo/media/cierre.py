"""La tarjeta final del video: la portada de la tienda (D10 de fabrica-de-publicaciones).

Mario, al ver el primer video real: lo que sale al final no se lee; al final va la portada de
apolocad.com con el dominio, y las cifras se ven ya dentro de la tienda. Por eso el cierre es
el hero de la tienda en modo oscuro (`app/globals.css` de la tienda, tema `marca-oscuro`): la A
de taller, el lema en blanco y negrita con el SUBRAYADO azul redondeado bajo su última línea
(como `TituloDeLaPortada.js`: trazo grueso, puntas redondas, 2 % más ancho por lado), el dominio
en ámbar y, al pie, chico y apagado, el aviso de responsabilidad (D8).

Textos (`textos_cierre`): el lema es `cierre.texto` del guion; vacío o el texto de antes
(«Descarga los planos…», un guion viejo) → `APOLO_TIENDA_LEMA` o `LEMA`. El dominio es el host
de `cierre.url` (la página de la máquina) sin `www.`; sin URL, el de `APOLO_TIENDA_URL` o
`DOMINIO`. Lo dibujan VTK (el video de la fábrica, fuera del núcleo) y el navegador
(`media/tarjetas.py`).

La A se dibuja aquí con la geometría de `docs/marca/apolo-icono.svg` (la carpeta `docs/` no
viaja en el paquete de PyPI); `tests/test_media_cierre.py` exige que coincida con el maestro.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from PIL import Image, ImageDraw

from .composicion import ESTILO, Estilo, _alto_linea, _una_linea, cargar_fuente, envolver

#: El lema de la tienda (`tienda.lema` de apolocad.com). Copia: `services/guion_video.CIERRE`
#: (services no importa media); un test exige que sean iguales.
LEMA = "Máquinas listas para fabricar"
DOMINIO = "apolocad.com"
LEMA_ENV = "APOLO_TIENDA_LEMA"
URL_ENV = "APOLO_TIENDA_URL"
#: Lo que escribían los guiones de antes en `cierre.texto`: ahora da el lema.
LEGADO = ("Descarga los planos y el modelo 3D",)
#: D8: la misma idea que la descripción de YouTube, en una línea corta.
AVISO_CIERRE = ("Diseño generado y validado por software: no fue construido ni probado "
                "físicamente.")

#: Tema oscuro de la tienda y colores de la marca (`docs/marca/README.md`).
FONDO = (15, 21, 27)          # --lienzo
REJILLA = (31, 41, 50)        # --linea-2
BLANCO = (255, 255, 255)
ACENTO = (91, 140, 255)       # --acento: el subrayado del lema
AMBAR = (240, 180, 60)        # --cota: el dominio y el travesaño de la A
APAGADO = (133, 145, 156)     # --tinta-3: el aviso
AZUL_MARCA = (44, 95, 212)    # el cuadrado de la A
#: La A de taller en su viewBox de 64 (el maestro SVG).
ICONO_LADO, ICONO_RADIO = 64.0, 14.0
ICONO_A = ([(16.0, 52.0), (32.0, 12.0), (48.0, 52.0)], 6.5)
ICONO_TRAVESANO = ([(21.5, 39.5), (42.5, 39.5)], 5.5)
#: El subrayado de la tienda: path «M2 8 C 50 2, 120 2, 198 7» en una caja de 200 × 12, trazo 5.
_CURVA = ((2, 8), (50, 2), (120, 2), (198, 7))
_SS = 4  # sobremuestreo de los trazos (Pillow no suaviza polígonos)


# ── Textos ────────────────────────────────────────────────────────────────────


def _host(url: str) -> str:
    try:
        host = urlsplit((url or "").strip()).hostname or ""
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def lema_por_defecto(entorno=None) -> str:
    entorno = os.environ if entorno is None else entorno
    return (entorno.get(LEMA_ENV) or "").strip() or LEMA


def textos_cierre(g: dict, entorno=None) -> tuple[str, str]:
    """(lema, dominio) del cierre del guion `g` (reglas en el docstring del módulo)."""
    entorno = os.environ if entorno is None else entorno
    texto = (g["cierre"].get("texto") or "").strip()
    lema = texto if texto and texto not in LEGADO else lema_por_defecto(entorno)
    dominio = (_host(g["cierre"].get("url") or "") or _host(entorno.get(URL_ENV) or "")
               or DOMINIO)
    return lema, dominio


# ── Maqueta ───────────────────────────────────────────────────────────────────

Caja = tuple[int, int, int, int]


@dataclass(frozen=True)
class MaquetaCierre:
    """Dónde va cada cosa (cajas x0, y0, x1, y1 en px del cuadro). `lema` = (texto, x centro,
    y arriba) por línea; ninguna caja sale del cuadro ni pisa a otra (lo prueban los tests)."""

    logo: Caja
    lema: list[tuple[str, int, int]]
    tam_lema: int
    cajas_lema: list[Caja]
    subrayado: Caja
    dominio: tuple[str, int, int]
    tam_dominio: int
    caja_dominio: Caja
    aviso: list[tuple[str, int, int]]
    cajas_aviso: list[Caja]


def _caja(fuente, texto: str, cx: float, y: float) -> Caja:
    x0, y0, x1, y1 = fuente.getbbox(texto, anchor="mt")
    return (round(cx + x0), round(y + y0), round(cx + x1), round(y + y1))


def _lineas_lema(lema: str, estilo: Estilo, tam: int, ancho_max: float):
    """Las líneas del lema a `tam` px si entra ENTERO (sin partir palabras) en ≤ 3, con el
    ancho más angosto que da las mismas líneas (parejas, como `text-balance`); si no, None."""
    f = cargar_fuente(estilo, tam, titulo=True)
    lineas = envolver(lema, f, ancho_max)
    if len(lineas) > 3 or " ".join(lineas).split() != lema.split():
        return None
    ancho, paso = ancho_max, max(1, tam // 6)
    while ancho - paso > 0:
        prueba = envolver(lema, f, ancho - paso)
        if len(prueba) != len(lineas) or " ".join(prueba).split() != lema.split():
            break
        ancho, lineas = ancho - paso, prueba
    return lineas


def maquetar_cierre(lema: str = LEMA, dominio: str = DOMINIO, estilo: Estilo = ESTILO,
                    aviso: str = AVISO_CIERRE) -> MaquetaCierre:
    """El cierre en `estilo`: logo, lema (la letra más grande con la que entra entero en ≤ 3
    líneas y cabe el bloque), subrayado, dominio y el aviso pegado abajo."""
    W, H, px = estilo.ancho, estilo.alto, estilo.px
    m = px(estilo.margen)
    ancho_util = W - 2 * m
    ancho_lema = min(ancho_util, px(1300)) if W > H else ancho_util
    f_av = cargar_fuente(estilo, px(26))
    lineas_av = envolver(aviso, f_av, min(ancho_util, px(1400)), 2) if aviso else []
    alto_av = _alto_linea(f_av) * len(lineas_av)
    fondo_bloque = H - px(56) - alto_av - (px(40) if lineas_av else 0)
    dominio_s, f_dom = _una_linea(dominio, estilo, px(80), px(36), ancho_util, titulo=True)
    lado = px(132)
    for tam in range(px(124), px(48) - 1, -max(1, px(124) // 16)):
        lineas = _lineas_lema(lema, estilo, tam, ancho_lema)
        f = cargar_fuente(estilo, tam, titulo=True)
        if lineas is None and tam > px(48):
            continue
        lineas = lineas or envolver(lema, f, ancho_lema, 3)
        paso = _alto_linea(f, 1.04)
        alto_sub = round(tam * 0.38)
        alto = (lado + px(52) + paso * len(lineas) + alto_sub + px(56)
                + _alto_linea(f_dom, 1.0))
        if m + alto <= fondo_bloque or tam <= px(48):
            break
    y = max(m, (fondo_bloque + m - alto) / 2)  # centrado en el espacio sobre el aviso
    cx = W / 2
    logo = (round(cx - lado / 2), round(y), round(cx - lado / 2) + lado, round(y) + lado)
    y += lado + px(52)
    lin, cajas = [], []
    for s in lineas:
        lin.append((s, round(cx), round(y)))
        cajas.append(_caja(f, s, cx, y))
        y += paso
    ultima = cajas[-1]
    ancho_ult = ultima[2] - ultima[0]
    # bajo la línea base de la última línea, como en la tienda (cruza los descendentes)
    y_sub = lin[-1][2] + f.getmetrics()[0] + round(tam * 0.03)
    sub = (round(ultima[0] - 0.02 * ancho_ult), y_sub,
           round(ultima[2] + 0.02 * ancho_ult), y_sub + alto_sub)
    y = max(y, sub[3]) + px(56)
    dom = (dominio_s, round(cx), round(y))
    caja_dom = _caja(f_dom, dominio_s, cx, y)
    av, cajas_av = [], []
    y = H - px(56) - alto_av
    for s in lineas_av:
        av.append((s, round(cx), round(y)))
        cajas_av.append(_caja(f_av, s, cx, y))
        y += _alto_linea(f_av)
    return MaquetaCierre(logo, lin, tam, cajas, sub, dom, f_dom.size, caja_dom, av, cajas_av)


# ── Dibujo ────────────────────────────────────────────────────────────────────


def _trazo(draw, puntos, ancho: float, color) -> None:
    """Polilínea con puntas y uniones redondas (`stroke-linecap/linejoin="round"`)."""
    r = ancho / 2
    for (x0, y0), (x1, y1) in zip(puntos, puntos[1:]):
        dx, dy = x1 - x0, y1 - y0
        largo = max((dx * dx + dy * dy) ** 0.5, 1e-9)
        nx, ny = -dy / largo * r, dx / largo * r
        draw.polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny),
                      (x0 - nx, y0 - ny)], fill=color)
    for x, y in puntos:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def logo(lado: int) -> Image.Image:
    """La A de taller (RGBA, `lado` px), dibujada a 4× y reducida para suavizar los bordes."""
    n = lado * _SS
    k = n / ICONO_LADO
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle([0, 0, n - 1, n - 1], radius=ICONO_RADIO * k, fill=(*AZUL_MARCA, 255))
    for (puntos, ancho), color in ((ICONO_A, BLANCO), (ICONO_TRAVESANO, AMBAR)):
        _trazo(draw, [(x * k, y * k) for x, y in puntos], ancho * k, (*color, 255))
    return im.resize((lado, lado), Image.Resampling.LANCZOS)


def _subrayado(ancho: int, alto: int) -> Image.Image:
    """El trazo de la tienda en una capa RGBA de `ancho` × `alto` (el grueso cabe adentro)."""
    w, h = ancho * _SS, alto * _SS
    grueso = 5 / 12 * h
    sx, sy = (w - grueso) / 200, (h - grueso) / 12
    p0, p1, p2, p3 = _CURVA
    puntos = []
    for i in range(41):
        t = i / 40
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        puntos.append((grueso / 2 + sx * (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0]),
                       grueso / 2 + sy * (a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])))
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    _trazo(ImageDraw.Draw(im), puntos, grueso, (*ACENTO, 255))
    return im.resize((ancho, alto), Image.Resampling.LANCZOS)


def _fondo(estilo: Estilo) -> Image.Image:
    """La tinta casi negra del hero con su rejilla técnica, que se apaga hacia los bordes."""
    tam = (estilo.ancho, estilo.alto)
    im = Image.new("RGB", tam, FONDO)
    rejilla = Image.new("RGB", tam, FONDO)
    draw = ImageDraw.Draw(rejilla)
    paso = estilo.px(64)
    for x in range(estilo.ancho // 2 % paso, estilo.ancho, paso):
        draw.line([(x, 0), (x, estilo.alto)], fill=REJILLA, width=1)
    for y in range(estilo.alto // 2 % paso, estilo.alto, paso):
        draw.line([(0, y), (estilo.ancho, y)], fill=REJILLA, width=1)
    mascara = Image.radial_gradient("L").resize(tam).point(lambda v: max(0, 255 - v * 2))
    return Image.composite(rejilla, im, mascara)


def cierre(lema: str = LEMA, dominio: str = DOMINIO, estilo: Estilo = ESTILO,
           aviso: str = AVISO_CIERRE) -> Image.Image:
    """La tarjeta final (RGB del tamaño del estilo): la portada de la tienda (D10)."""
    mq = maquetar_cierre(lema, dominio, estilo, aviso)
    im = _fondo(estilo)
    x0, y0, x1, _ = mq.logo
    a = logo(x1 - x0)
    im.paste(a, (x0, y0), a)
    sx0, sy0, sx1, sy1 = mq.subrayado
    sub = _subrayado(sx1 - sx0, sy1 - sy0)
    im.paste(sub, (sx0, sy0), sub)  # bajo el texto: las letras con descendente lo pisan
    draw = ImageDraw.Draw(im)
    f = cargar_fuente(estilo, mq.tam_lema, titulo=True)
    for s, x, y in mq.lema:
        draw.text((x, y), s, font=f, fill=BLANCO, anchor="mt")
    s, x, y = mq.dominio
    draw.text((x, y), s, font=cargar_fuente(estilo, mq.tam_dominio, titulo=True), fill=AMBAR,
              anchor="mt")
    f_av = cargar_fuente(estilo, estilo.px(26))
    for s, x, y in mq.aviso:
        draw.text((x, y), s, font=f_av, fill=APAGADO, anchor="mt")
    return im
