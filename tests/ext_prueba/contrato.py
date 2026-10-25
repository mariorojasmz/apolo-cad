"""Lo que la extensión falsa LEE por el contrato (plan pedidos-de-extensiones, D1 y D13 de
lectura): todo de módulos de `extensiones_api.MODULOS` con los nombres que declara (el gate de
imports de `test_extensiones_api.py` lo exige). Es lo que hacían por fuera las dos extensiones que
pidieron estos puntos: resolver un borne con la regla del núcleo, dibujar el pilotaje a trazos con
su medida, saber si hay DWG, leer la FAT del núcleo (los escenarios con su vigencia) y leer un
fotograma de la sesión viva con la tabla del `inicio`.
"""

from __future__ import annotations

import math

from apolo.cosim.vivo_fotograma import CABECERA, FORMATO, leer_fotograma
from apolo.drawing.dwg import DwgError, disponible, sheet_to_dwg
from apolo.drawing.esquema import (
    GROSOR_SIMBOLO_MM,
    HUECO_X_GROSOR,
    PILOTAJE,
    TRAZO_X_GROSOR,
    pilotaje,
    trazos_mm,
)
from apolo.drawing.sheet import SheetModel
from apolo.library.electrico.redes import resolver
from apolo.services.electrico import modelo
from apolo.services.escenarios import SIN_CORRER, VENCIDO, estado, firma_documento, listar


def bornes(doc, puntos: list[str]) -> dict:
    """{punto: [designación, borne]} o {punto: motivo}, con la MISMA regla que el carril."""
    por_des = {d.designacion: d for d in modelo(doc).dispositivos}
    out = {}
    for p in puntos:
        res, motivo = resolver(p, por_des)
        out[p] = list(res) if res else motivo
    return out


def envolvente(m: SheetModel, x0: float, y0: float, x1: float, y1: float) -> tuple[float, float]:
    """La envolvente a trazos de un conjunto (cuatro líneas de pilotaje); devuelve (trazo, hueco)
    en mm, que la extensión usa para su propio exportador."""
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)),
                 ((x0, y1), (x0, y0))):
        linea = pilotaje(m, *a, *b)
        assert linea.kind == PILOTAJE
    trazo, hueco = trazos_mm()
    assert (trazo, hueco) == (TRAZO_X_GROSOR * GROSOR_SIMBOLO_MM, HUECO_X_GROSOR * GROSOR_SIMBOLO_MM)
    return trazo, hueco


def dwg(m: SheetModel) -> dict:
    """La lámina en DWG si hay conversor; si no, el aviso del núcleo (sin lanzar)."""
    hay = disponible()
    if not hay["disponible"]:
        return {"dwg": None, "aviso": hay["aviso"]}
    try:
        return {"dwg": sheet_to_dwg(m), "aviso": None}
    except DwgError as exc:
        return {"dwg": None, "aviso": str(exc)}


def fat(doc) -> dict:
    """La FAT del núcleo: cada escenario con su estado y si su resultado sigue vigente."""
    lista = listar(doc)
    firma = firma_documento(doc)
    assert lista["firma_documento"] == firma
    filas = []
    for fila in lista["escenarios"]:
        st = estado(doc, fila["nombre"], firma)
        assert st["estado"] == fila["estado"]
        filas.append({"nombre": fila["nombre"], "estado": st["estado"],
                      "vigente": st["estado"] not in (SIN_CORRER, VENCIDO)})
    return {"firma": firma, "escenarios": filas}


def fotograma(datos: bytes, senales: list[str]) -> dict:
    """Un fotograma del vivo con los nombres de la tabla (`inicio.senales` + las `senales` que
    llegaron después): {t, factor, valores} sin los NaN (señal que ese intercambio no trajo)."""
    if len(datos) < 4 * CABECERA:
        raise ValueError("fotograma más corto que su cabecera")
    f = leer_fotograma(datos)
    if f["formato"] != FORMATO:
        raise ValueError(f"fotograma de formato {f['formato']}; esta extensión lee el {FORMATO}")
    valores = {n: float(v) for n, v in zip(senales, f["senales"]) if not math.isnan(float(v))}
    return {"t": f["t"], "factor": f["factor"], "valores": valores}
