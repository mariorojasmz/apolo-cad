"""Las filas del costeo de la extensión falsa (`Extension.costeo`; plan
puntos-de-extension-entregables, D2):

- «prueba.revision»: una revisión de 1,5 h a 20 USD/h en todo documento;
- «prueba.conexionado»: con tablero, una conexión por conductor a 2 USD (lee el modelo eléctrico
  por la superficie, `electrico.resumen`).

Y las variantes que el núcleo rechaza al cargar o descarta al costear (`test_extensiones_entregables.py`).
"""

from __future__ import annotations

from apolo.extensiones_api import FuenteCosteo

from .electrico import resumen


def _revision(_doc) -> list[dict]:
    return [{"descripcion": "Revisión de prueba", "cantidad": 1.5, "unidad": "h",
             "costo_unit": 20, "fuente": "criterio de prueba (20 USD/h)"}]


def _conexionado(doc) -> list[dict]:
    n = resumen(doc)["conductores"]
    if not n:
        return []
    return [{"descripcion": "Conexionado de prueba", "cantidad": n, "unidad": "conexión",
             "costo_unit": 2.0, "fuente": "criterio de prueba (2 USD por conexión)",
             "categoria": "mano de obra"}]


REVISION = FuenteCosteo("prueba.revision", _revision)
CONEXIONADO = FuenteCosteo("prueba.conexionado", _conexionado)


def fuentes() -> list:
    return [REVISION, CONEXIONADO]


# ── lo que no carga ──────────────────────────────────────────────────────────────────────────
def sin_prefijo() -> list:
    return [FuenteCosteo("revision", _revision)]


def repetida() -> list:
    return [REVISION, REVISION]


def no_es_fuente() -> list:
    return [{"id": "prueba.dict", "filas": _revision}]


def no_llamable() -> list:
    return [FuenteCosteo("prueba.fija", [{"descripcion": "x"}])]


# ── lo que carga y el costeo descarta con un aviso ───────────────────────────────────────────
def _malas(_doc) -> list:
    return [{"descripcion": "Infinita", "cantidad": float("inf"), "unidad": "h", "costo_unit": 1,
             "fuente": "x"},
            {"descripcion": "Con clave de más", "cantidad": 1, "unidad": "h", "costo_unit": 1,
             "fuente": "x", "descuento": 5},
            {"descripcion": "Precio negativo", "cantidad": 1, "unidad": "h", "costo_unit": -3,
             "fuente": "x"},
            {"descripcion": "Booleana", "cantidad": True, "unidad": "h", "costo_unit": 1,
             "fuente": "x"},
            {"descripcion": "Buena", "cantidad": 2, "unidad": "u", "costo_unit": 0.5,
             "fuente": "criterio de prueba"}]


def _lanza(_doc):
    raise RuntimeError("la fuente de prueba se rompió")


def con_fallas() -> list:
    return [FuenteCosteo("prueba.malas", _malas), FuenteCosteo("prueba.lanza", _lanza)]
