"""Las imágenes fijas del video que graba el navegador (plan video-realista, D5): portada, cierre
y el rótulo de cada etapa, dibujadas con las MISMAS funciones de `composicion.py` y `cierre.py`
que el video de VTK. El navegador las pide a la API y las pone sobre su cuadro: el texto y su aspecto
son los mismos en los dos videos.

Puro: recibe el guion (un dict ya validado) y, para la portada, la foto de la máquina terminada
que subió el navegador. Devuelve PNG en bytes.
"""

from __future__ import annotations

import io
from dataclasses import replace

#: Las cifras ya no salen en el video (D10 de fabrica-de-publicaciones): las muestra la tienda.
PARTES = ("portada", "cierre")


class TarjetaError(ValueError):
    pass


def _estilo(ancho: int, alto: int):
    from . import composicion as comp

    return replace(comp.ESTILO, ancho=ancho, alto=alto)


def _png(imagen) -> bytes:
    buf = io.BytesIO()
    imagen.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def tarjeta(g: dict, parte: str, ancho: int, alto: int, foto=None) -> bytes:
    """La tarjeta `parte` del guion `g` (RGB, del tamaño del video). La portada va sobre `foto`
    (una `PIL.Image`) como en VTK; sin foto, sobre el degradado."""
    from . import composicion as comp

    estilo = _estilo(ancho, alto)
    if parte == "portada":
        return _png(comp.portada(g["titulo"], g["subtitulo"], fondo=foto, estilo=estilo))
    if parte == "cierre":
        from .cierre import cierre, textos_cierre

        lema, dominio = textos_cierre(g)
        return _png(cierre(lema, dominio, estilo))
    raise TarjetaError(f"La tarjeta «{parte}» no existe (son: {', '.join(PARTES)}).")


def rotulo(g: dict, etapa: int, ancho: int, alto: int) -> bytes:
    """El rótulo de la etapa `etapa` como capa RGBA transparente del tamaño del video."""
    from . import composicion as comp

    if not 0 <= etapa < len(g["etapas"]):
        raise TarjetaError(f"El guion tiene {len(g['etapas'])} etapas: la {etapa} no existe.")
    e = g["etapas"][etapa]
    return _png(comp.capa_rotulo(e["titulo"], e["texto"], _estilo(ancho, alto)))


def miniatura(g: dict, foto, ruta):
    """La miniatura de YouTube (D15) desde la foto de la máquina terminada, como la de VTK."""
    from . import composicion as comp

    return comp.guardar_miniatura(comp.miniatura(foto, g["titulo"]), ruta)
