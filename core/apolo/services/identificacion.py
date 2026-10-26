"""A quién va la cotización (plan cotizacion-identificada-y-ajustes-por-escenario, D1–D2), sobre el
`doc` explícito (el llamador sostiene STATE_LOCK).

Precedencia: la identificación comercial del PROYECTO (`doc.comercial`, entera) → la primera
`IdentificacionCosteo` de una extensión que devuelva algo válido → nada (la cotización se titula
con el nombre limpio del proyecto y no lleva bloque de cliente). La fuente queda dicha en
`fuente`: «proyecto», el id de la identificación de la extensión, o «nombre».
"""

from __future__ import annotations

import sys


def poner_comercial(doc, fields) -> dict:
    """Reemplaza el metadato `doc.comercial` (D1; manifest, fuera del log: se escribe sólo si
    hay) con `fields` validado (`library/comercial.normalizar`; `{}` lo borra) y lo devuelve.
    `ValueError` con el motivo, sin tocar nada. Setter en `services`, como `poner_funciones`: el
    `dir(Document)` está congelado (`tests/test_rutas_viejas.py`)."""
    from apolo.library.comercial import normalizar

    doc.comercial = normalizar(fields)
    return doc.comercial


def identificacion(doc) -> dict:
    """`{titulo?, cliente?, numero?, revision?, fuente}`. Una identificación de extensión que lanza
    o devuelve algo que no valida se salta (con su motivo en stderr): nunca tumba la cotización."""
    from apolo.library import costeo_extension
    from apolo.library.comercial import normalizar

    propio = getattr(doc, "comercial", None) or {}
    if propio:
        try:
            return {**normalizar(propio), "fuente": "proyecto"}
        except ValueError as exc:  # un manifest editado a mano: la carga no valida
            print(f"apolo: la identificación comercial del proyecto no vale: {exc}",
                  file=sys.stderr)
    for nombre, ident in costeo_extension.identificaciones():
        try:
            limpio = normalizar(ident.de_documento(doc))
        except Exception as exc:  # noqa: BLE001 — el código de la extensión puede lanzar
            print(f"apolo: la identificación «{ident.id}» de la extensión {nombre} se salta: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if limpio:
            return {**limpio, "fuente": ident.id}
    return {"fuente": "nombre"}
