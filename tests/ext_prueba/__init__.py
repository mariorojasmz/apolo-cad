"""Extensión FALSA de la suite (D9 del plan nucleo-abierto-extensiones-privadas): usa cada punto
de extensión del núcleo con lo mínimo, sin instalarse (se carga con
`APOLO_EXTENSIONES_EXTRA=ext_prueba:EXTENSION`; `tests/` está en el `sys.path` de la suite).

- un comando `prueba.hola` que crea una caja (`comandos.py`), con su pista y su pestaña;
- una ruta `GET /api/prueba/hola` (`rutas.py`);
- una tool MCP `prueba_hola` que corre el comando (`tools.py`);
- un YAML de catálogo con UNA ref, `prueba.caja` (`catalogo/`);
- un modelo de co-simulación mínimo, tipo `prueba.lampara` (`modelos.py`);
- (F1d) rutas que leen y mutan el documento por la fachada y guardan sus datos en la clave `ext`
  del manifest (`rutas.py`), dos ítems de la puerta de publicación (`puerta.py`) y una lámina
  con el motor de planos (`laminas.py`);
- (puntos-de-extension-entregables) la lectura eléctrica por `MODULOS` (`electrico.py`), dos
  fuentes de filas del costeo (`costeo.py`) y dos reglas de la puerta de entrega (`entrega.py`).
- (plc-en-el-lazo F1b1) un conector a un PLC de afuera, `prueba.tcp` (`conector_plc.py`: JSON
  por línea sobre TCP, su red en `red_plc.py`), contra un PLC falso en otro proceso
  (`plc_falso.py`).
- (plc-en-el-lazo F1c2) un suscriptor del bus de la sesión viva, `prueba.scada`
  (`suscriptor.py`: la sigue en su hilo con `suscribir` y le manda acciones con `enviar_vivo`).
- (pedidos-de-extensiones D13) la lectura por el contrato (`contrato.py`): bornes con la regla
  del carril, pilotaje a trazos, DWG, la FAT del núcleo y un fotograma del vivo; y (D6) un
  entregable en archivo por `entregable_documento`, en directo o como job (`rutas.py`), que su
  tool `prueba_informe` pide con `pedir_entregable` (`tools.py`); (D9) sus dos fuentes de costeo
  llevan nota para la cotización (`costeo.py`).

Los campos pesados van PEREZOSOS (funciones): así lo hace una extensión real para que el MCP no
cargue OCCT al leerla. Abajo, las variantes que el núcleo debe RECHAZAR (`test_extensiones.py`).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from apolo.extensiones_api import Extension

from .tools import registrar, registrar_con_punto

CATALOGO = Path(__file__).resolve().parent / "catalogo"


def _comandos():
    from .comandos import SPECS

    return SPECS


def _routers():
    from .rutas import router

    return [router]


def _modelos():
    from .modelos import Lampara

    return {"prueba.lampara": Lampara}


def _conectores(variante: str = "ConectorTCP", nombre: str = "prueba.tcp"):
    def cargar():
        from . import conector_plc

        return {nombre: getattr(conector_plc, variante)}

    return cargar


def _puerta(variante: str = "entradas"):
    def cargar():
        from . import puerta

        return getattr(puerta, variante)()

    return cargar


def _de(modulo: str, variante: str):
    """Una lista perezosa de `ext_prueba.<modulo>.<variante>()` (carga OCCT sólo al resolverla)."""
    def cargar():
        import importlib

        return getattr(importlib.import_module(f"{__name__}.{modulo}"), variante)()

    return cargar


EXTENSION = Extension(
    nombre="ext-prueba",
    prefijo="prueba",
    version="0.1.0",
    nucleo=(1, 1),
    comandos=_comandos,
    pistas={"prueba.hola": "Crea una caja de prueba para comprobar que la extensión se cargó."},
    pestanas={"prueba": {"orden": 90, "rotulo": "Prueba"}},
    routers=_routers,
    tools_mcp=registrar,
    catalogo=(str(CATALOGO),),
    modelos_cosim=_modelos,
    conectores_plc=_conectores(),
    epoch_catalogo=1,
    puerta=_puerta(),
    version_puerta=1,
    costeo=_de("costeo", "fuentes"),
    version_costeo=1,
    entrega=_de("entrega", "reglas"),
    version_entrega=1,
)


def _sin_prefijo():
    from .comandos import sin_prefijo

    return [sin_prefijo()]


def _electrico():
    from .comandos import electrico

    return [electrico()]


def _routers_fea():
    from .rutas import router_fea

    return [router_fea]


# ── lo que el núcleo rechaza (todo o nada: nada de la extensión queda registrado) ──────────────
SIN_PREFIJO = replace(EXTENSION, comandos=_sin_prefijo)
CONTRATO_VIEJO = replace(EXTENSION, nombre="ext-vieja", nucleo=(2, 3))
ELECTRICA = replace(EXTENSION, comandos=_electrico)
TOOL_CON_PUNTO = replace(EXTENSION, tools_mcp=registrar_con_punto)
DUPLICADA = replace(EXTENSION, nombre="ext-prueba-2")  # mismo prefijo que EXTENSION
EN_RUTAS_DEL_NUCLEO = replace(EXTENSION, nombre="ext-fea", prefijo="fea", comandos=(), pistas={},
                              pestanas={}, catalogo=(), modelos_cosim={}, conectores_plc={}, tools_mcp=None,
                              puerta=(), costeo=(), entrega=(), routers=_routers_fea)
PUERTA_SIN_PREFIJO = replace(EXTENSION, puerta=_puerta("sin_prefijo"))
PUERTA_FAMILIA = replace(EXTENSION, puerta=_puerta("familia_inventada"))
PUERTA_REPETIDA = replace(EXTENSION, puerta=_puerta("repetida"))
PUERTA_NO_ENTRADA = replace(EXTENSION, puerta=_puerta("no_es_entrada"))
PUERTA_V2 = replace(EXTENSION, version_puerta=2)
# costeo y entrega (plan puntos-de-extension-entregables)
COSTEO_SIN_PREFIJO = replace(EXTENSION, costeo=_de("costeo", "sin_prefijo"))
COSTEO_REPETIDO = replace(EXTENSION, costeo=_de("costeo", "repetida"))
COSTEO_NO_FUENTE = replace(EXTENSION, costeo=_de("costeo", "no_es_fuente"))
COSTEO_NO_LLAMABLE = replace(EXTENSION, costeo=_de("costeo", "no_llamable"))
COSTEO_VERSION_MALA = replace(EXTENSION, version_costeo=0)
COSTEO_CON_FALLAS = replace(EXTENSION, costeo=_de("costeo", "con_fallas"))
COSTEO_V3 = replace(EXTENSION, version_costeo=3)
# notas de la cotización (plan pedidos-de-extensiones, D9 y D13)
COSTEO_NOTAS_LARGAS = replace(EXTENSION, costeo=_de("costeo", "notas_largas"))
NOTA_VACIA = replace(EXTENSION, costeo=_de("costeo", "nota_vacia"))
NOTA_DOS_LINEAS = replace(EXTENSION, costeo=_de("costeo", "nota_dos_lineas"))
NOTA_LARGA = replace(EXTENSION, costeo=_de("costeo", "nota_larga"))
NOTA_NO_TEXTO = replace(EXTENSION, costeo=_de("costeo", "nota_no_texto"))
# la cotización identificada (plan cotizacion-identificada-y-ajustes-por-escenario, F1)
COSTEO_IDENTIFICADA = replace(EXTENSION, costeo=_de("costeo", "identificada"))
COSTEO_ACOTA_ALCANCE = replace(EXTENSION, costeo=_de("costeo", "acota_alcance"))
COSTEO_IDENTIFICACION_ROTA = replace(EXTENSION, costeo=_de("costeo", "identificacion_rota"))
ACOTA_HONESTIDAD = replace(EXTENSION, costeo=_de("costeo", "acota_honestidad"))
ACOTA_SIN_NOTA = replace(EXTENSION, costeo=_de("costeo", "acota_sin_nota"))
ACOTA_INVENTADA = replace(EXTENSION, costeo=_de("costeo", "acota_inventada"))
ACOTA_DOBLE = replace(EXTENSION, costeo=_de("costeo", "acota_doble"))
INCLUYE_MALO = replace(EXTENSION, costeo=_de("costeo", "incluye_malo"))
IDENTIFICACION_NO_LLAMABLE = replace(EXTENSION, costeo=_de("costeo", "identificacion_no_llamable"))
COSTEO_IDENTIFICADA_CON_ROTULO = replace(EXTENSION, costeo=_de("costeo", "identificada_con_rotulo"))
ROTULO_DOS_LINEAS = replace(EXTENSION, costeo=_de("costeo", "rotulo_dos_lineas"))
ROTULO_LARGO = replace(EXTENSION, costeo=_de("costeo", "rotulo_largo"))
ROTULO_VACIO = replace(EXTENSION, costeo=_de("costeo", "rotulo_vacio"))
#: otra extensión (sólo costeo) que acota la misma nota que COSTEO_IDENTIFICADA: no carga
OTRA_VALIDEZ = Extension(nombre="ext-otra", prefijo="otra", version="0.1.0",
                         costeo=_de("costeo", "otra_validez"))
ENTREGA_SIN_PREFIJO = replace(EXTENSION, entrega=_de("entrega", "sin_prefijo"))
ENTREGA_REPETIDA = replace(EXTENSION, entrega=_de("entrega", "repetida"))
ENTREGA_SIN_TITULO = replace(EXTENSION, entrega=_de("entrega", "sin_titulo"))
ENTREGA_NO_REGLA = replace(EXTENSION, entrega=_de("entrega", "no_es_regla"))
ENTREGA_VERSION_MALA = replace(EXTENSION, version_entrega=True)
ENTREGA_ROTA = replace(EXTENSION, entrega=_de("entrega", "rotas"))
ENTREGA_V2 = replace(EXTENSION, version_entrega=2)
# conectores a un PLC de afuera (plan plc-en-el-lazo, D5)
CONECTOR_SIN_PREFIJO = replace(EXTENSION, conectores_plc=_conectores(nombre="tcp"))
CONECTOR_INCOMPLETO = replace(EXTENSION, conectores_plc=_conectores("SinPaso"))
CONECTOR_SIN_VALIDAR = replace(EXTENSION, conectores_plc=_conectores("SinValidar"))
CONECTOR_OPCIONAL_MALO = replace(EXTENSION, conectores_plc=_conectores("CerrarNoLlamable"))
CONECTOR_NO_CLASE = replace(EXTENSION, conectores_plc={"prueba.tcp": "no es una clase"})
NO_ES_EXTENSION = "una cadena no es una extensión"
