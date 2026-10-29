"""Memos EXACTOS de una corrida (plan puerta-rapida, D3): lo que la puerta de publicación
recalcula igual en cada prueba de sobrantes (el volumen de cada forma, la viga continua por sus
entradas, la carrera de la plantilla por sus params) se calcula una vez mientras dura el `with`.

Viven en un `ContextVar` que abre `memo_de_corrida` (lo abre `mass.memo_de_geometria`, que abre
`puerta_publicacion.reunir`): fuera de un `with` no hay memo y todo se calcula como siempre; al
salir se tira (sin estado global, raíz § Escala). Sólo se memoiza lo PURO cuyo resultado nadie
muta (un número o una dataclass congelada); una excepción no se guarda: se vuelve a lanzar en
cada llamada. Por forma: por `id` guardando la REFERENCIA y verificando `is`
(core/apolo/CLAUDE.md). Por clave: `pickle` de los argumentos, que distingue el tipo (1 y 1.0
no son la misma entrada: el resultado podría escribirse distinto) y el signo del cero.
"""

from __future__ import annotations

import pickle
from contextlib import contextmanager
from contextvars import ContextVar

_MEMO: ContextVar[dict | None] = ContextVar("memo_corrida", default=None)


@contextmanager
def memo_de_corrida():
    """Mientras dura, los memos de esta corrida están abiertos (anidable: el de afuera manda)."""
    if _MEMO.get() is not None:
        yield
        return
    token = _MEMO.set({})
    try:
        yield
    finally:
        _MEMO.reset(token)


def abierto() -> bool:
    return _MEMO.get() is not None


def _tabla(nombre: str) -> dict | None:
    memo = _MEMO.get()
    return None if memo is None else memo.setdefault(nombre, {})


def por_forma(nombre: str, forma, calcular):
    """`calcular()` una vez por `forma` (objeto OCCT) en la corrida; sin memo abierto, siempre."""
    tabla = _tabla(nombre)
    if tabla is None:
        return calcular()
    hit = tabla.get(id(forma))
    if hit is not None and hit[0] is forma:
        return hit[1]
    valor = calcular()
    tabla[id(forma)] = (forma, valor)
    return valor


def por_clave(nombre: str, calcular, *args, **kwargs):
    """`calcular(*args, **kwargs)` una vez por argumentos (iguales por `pickle`) en la corrida."""
    tabla = _tabla(nombre)
    if tabla is None:
        return calcular(*args, **kwargs)
    try:
        clave = pickle.dumps((args, sorted(kwargs.items())), protocol=4)
    except Exception:  # noqa: BLE001 — un argumento que no se serializa: sin memo
        return calcular(*args, **kwargs)
    if clave in tabla:
        return tabla[clave]
    valor = calcular(*args, **kwargs)
    tabla[clave] = valor
    return valor


def volumen(forma) -> float:
    """`float(forma.volume)` (la suma de sus sólidos si es un Compound), una vez por forma; lanza
    lo que lance OCCT, como sin memo (cada llamador decide su respaldo)."""
    return por_forma("volumen", forma, lambda: float(forma.volume))
