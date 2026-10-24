"""Una lámina de la extensión falsa con el motor de planos del núcleo (F1d): `drawing.sheet`,
`tabla`, `titleblock` y `pdf` están en `extensiones_api.MODULOS`, que se importan de su módulo
(no se re-exportan). Un entregable propio de una extensión se arma así: tabla paginada con su
cajetín y PDF multipágina."""

from __future__ import annotations

from apolo.drawing.pdf import sheets_to_pdf
from apolo.drawing.sheet import SHEETS, Label
from apolo.drawing.tabla import hojas_tabla
from apolo.drawing.titleblock import draw_title_block


def laminas(filas: list[list]) -> list:
    """Las hojas A4 apaisadas de una tabla «Ítem | Descripción | Cantidad», con su cajetín."""
    W, H = SHEETS["A4"]

    def cajetin(k: int, n: int) -> dict:
        return {"project": "Prueba de extensión", "drawing_no": "EXT-1", "scale": "—",
                "sheet": "Lista de prueba", "sheet_no": k, "n_sheets": n, "units": "mm"}

    hojas = hojas_tabla("LISTA DE PRUEBA", ["Ítem", "Descripción", "Cantidad"], filas, W=W, H=H,
                        meta_hoja=cajetin, flexibles={1}, derecha={2})
    for hoja in hojas:
        hoja.labels.append(Label(W / 2, H - 12, "EXTENSIÓN DE PRUEBA", size=4.0))
    return hojas


def cajetin_suelto(hoja) -> None:
    draw_title_block(hoja, {"project": "Prueba", "drawing_no": "EXT-2", "sheet": "Suelta"})


def pdf(filas: list[list]) -> bytes:
    return sheets_to_pdf(laminas(filas))
