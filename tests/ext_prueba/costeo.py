"""Las filas del costeo de la extensión falsa (`Extension.costeo`; plan
puntos-de-extension-entregables, D2):

- «prueba.revision»: una revisión de 1,5 h a 20 USD/h en todo documento;
- «prueba.conexionado»: con tablero, una conexión por conductor a 2 USD (lee el modelo eléctrico
  por la superficie, `electrico.resumen`).

Y las variantes que el núcleo rechaza al cargar o descarta al costear (`test_extensiones_entregables.py`).
"""

from __future__ import annotations

from apolo.extensiones_api import FuenteCosteo, IdentificacionCosteo

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


# ── la cotización identificada (plan cotizacion-identificada-y-ajustes-por-escenario, F1) ────
def _marcha(_doc) -> list[dict]:
    return [{"descripcion": "Prueba de marcha", "cantidad": 4, "unidad": "h", "costo_unit": 25,
             "fuente": "criterio de prueba (25 USD/h)", "categoria": "puesta en marcha"}]


def _gestion(_doc) -> list[dict]:
    return [{"descripcion": "Gestión de la oferta", "cantidad": 1, "unidad": "u", "costo_unit": 0,
             "fuente": "criterio de prueba"}]


def _cliente(doc):
    """La identificación de la extensión: sólo para los documentos «faja…» (los demás: None)."""
    if not str(doc.name).startswith("faja"):
        return None
    return {"cliente": "Cliente de la extensión", "numero": "EXT-0007"}


NOTA_VALIDEZ = "Validez de la oferta: 30 días calendario desde su emisión."
NOTA_ALCANCE = "Incluye transporte a obra en la ciudad; no incluye la instalación eléctrica."
MARCHA = FuenteCosteo("prueba.marcha", _marcha, incluye=("pruebas",))
VALIDEZ = FuenteCosteo("prueba.validez", _gestion, NOTA_VALIDEZ, acota="nucleo.validez")
CLIENTE = IdentificacionCosteo("prueba.cliente", _cliente)


def identificada() -> list:
    """Revisión con nota + la prueba de marcha (`incluye`) + la validez acotada + la identidad."""
    return [REVISION, MARCHA, VALIDEZ, CLIENTE]


def acota_alcance() -> list:
    return [FuenteCosteo("prueba.alcance", _gestion, NOTA_ALCANCE, acota="nucleo.alcance"), MARCHA]


def _identidad_que_lanza(_doc):
    raise RuntimeError("la identificación de prueba se rompió")


def identificacion_rota() -> list:
    """Una que lanza y una que no valida se saltan: gana la tercera."""
    return [IdentificacionCosteo("prueba.rota", _identidad_que_lanza),
            IdentificacionCosteo("prueba.mala", lambda _d: {"cliente": "X", "descuento": 5}),
            CLIENTE]


# ── lo que no carga (D3: honestidad, sin nota, inventada, doble dueño; D4: incluye; D2) ──────
def acota_honestidad() -> list:
    return [FuenteCosteo("prueba.revision", _revision, "Precios firmes.",
                         acota="nucleo.referenciales")]


def acota_sin_nota() -> list:
    return [FuenteCosteo("prueba.revision", _revision, acota="nucleo.validez")]


def acota_inventada() -> list:
    return [FuenteCosteo("prueba.revision", _revision, "x", acota="nucleo.garantia")]


def acota_doble() -> list:
    return [VALIDEZ, FuenteCosteo("prueba.otra", _gestion, "Validez: 60 días.",
                                  acota="nucleo.validez")]


def incluye_malo() -> list:
    return [FuenteCosteo("prueba.marcha", _marcha, incluye=("viaticos",))]


def identificacion_no_llamable() -> list:
    return [IdentificacionCosteo("prueba.cliente", {"cliente": "fijo"})]


#: El rótulo legible del pie de la cotización (en vez del id «prueba.cliente»).
ROTULO = "ficha comercial de prueba"


def identificada_con_rotulo() -> list:
    return [IdentificacionCosteo("prueba.cliente", _cliente, rotulo=ROTULO)]


def rotulo_dos_lineas() -> list:
    return [IdentificacionCosteo("prueba.cliente", _cliente, rotulo="ficha\ncomercial")]


def rotulo_largo() -> list:
    return [IdentificacionCosteo("prueba.cliente", _cliente, rotulo="x" * 61)]


def rotulo_vacio() -> list:
    return [IdentificacionCosteo("prueba.cliente", _cliente, rotulo="  ")]


#: El rótulo de la columna «Ref» de las filas de una fuente (en vez del id «prueba.revision»).
ROTULO_FUENTE = "Revisión técnica"


def fuente_con_rotulo() -> list:
    """«prueba.revision» con rótulo y «prueba.marcha» sin él (cae a su id)."""
    return [FuenteCosteo("prueba.revision", _revision, NOTA_REVISION, rotulo=ROTULO_FUENTE),
            FuenteCosteo("prueba.marcha", _marcha)]


def fuente_rotulo_dos_lineas() -> list:
    return [FuenteCosteo("prueba.revision", _revision, rotulo="Revisión\ntécnica")]


def fuente_rotulo_largo() -> list:
    return [FuenteCosteo("prueba.revision", _revision, rotulo="x" * 61)]


def fuente_rotulo_vacio() -> list:
    return [FuenteCosteo("prueba.revision", _revision, rotulo="  ")]


def otra_validez() -> list:
    """La de la extensión «ext-otra» (prefijo «otra»): acota lo mismo que `VALIDEZ`."""
    return [FuenteCosteo("otra.validez", _gestion, "Validez: 7 días.", acota="nucleo.validez")]
