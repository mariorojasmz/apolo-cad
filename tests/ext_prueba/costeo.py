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


#: las notas de la cotización (pedidos-de-extensiones D9): salen sólo si su fuente cobró
NOTA_REVISION = "La revisión de prueba no incluye visitas a obra."
NOTA_CONEXIONADO = "El conexionado de prueba se cobra por conductor del tablero."
REVISION = FuenteCosteo("prueba.revision", _revision, NOTA_REVISION)
CONEXIONADO = FuenteCosteo("prueba.conexionado", _conexionado, NOTA_CONEXIONADO)


def fuentes() -> list:
    return [REVISION, CONEXIONADO]


def _larga(tema: str) -> str:
    """Una nota de 300 caracteres justos, ancha (mayúsculas): el peor caso del resumen."""
    base = f"NOTA LARGA DE {tema}: ALCANCE, EXCLUSIONES Y CONDICIONES DEL SERVICIO COTIZADO "
    return (base * 10)[:299] + "."


LARGA_REVISION, LARGA_CONEXIONADO = _larga("REVISIÓN"), _larga("CONEXIONADO")


def notas_largas() -> list:
    """Las dos fuentes con notas de 300 caracteres (el peor caso de D9)."""
    return [FuenteCosteo("prueba.revision", _revision, LARGA_REVISION),
            FuenteCosteo("prueba.conexionado", _conexionado, LARGA_CONEXIONADO)]


# ── notas que no cargan (D9: no vacía, una línea, ≤ 300 caracteres) ─────────────────────────
def nota_vacia() -> list:
    return [FuenteCosteo("prueba.revision", _revision, "   ")]


def nota_dos_lineas() -> list:
    return [FuenteCosteo("prueba.revision", _revision, "Primera línea.\nSegunda línea.")]


def nota_larga() -> list:
    return [FuenteCosteo("prueba.revision", _revision, "x" * 301)]


def nota_no_texto() -> list:
    return [REVISION, FuenteCosteo("prueba.conexionado", _conexionado, 42)]


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
