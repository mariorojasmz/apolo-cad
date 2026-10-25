"""La CARA del PLC que usa la corrida (plan plc-en-el-lazo, D4): el PLC virtual o uno de afuera.

`Corrida` no necesita la clase `apolo.plc.PLC`: le alcanzan 13 miembros (medidos sobre
`corrida.py` y `planificador.py`), que `PLC` cumple tal cual. Un CONECTOR de extensión
(`Extension.conectores_plc`, D5) los cumple hablando con un PLC de verdad, o con el simulador de
su fabricante, y entra a la corrida sólo para la designación que el PEDIDO elige (D6).

Contrato de un conector («prefijo.x» → clase):
  - `Conector(programa, config)`: `programa` es el `datos.ProgramaCosim` de esa designación (su
    `compilado` da las entradas y salidas de la ficha) y `config` el dict del pedido. Construirlo
    CONECTA; si no puede, lanza `LazoCortado` y la corrida no arranca. Importa su librería de red
    al conectar, nunca al importarse su módulo: el worker lo des-serializa por pickle (D5).
  - `Conector.validar_config(config) -> list[str]`: PURO (sin red); cada texto dice qué corregir.
    La API lo llama ANTES del worker y una lista no vacía es 400.
  - los 13 miembros de `PuertoPLC`; los datos (`compilado`, `estado`, `salidas`, `falla`,
    `fallas`, `scans`) DECLARADOS en la clase (atributo, propiedad o anotación): así se valida al
    cargar la extensión, sin conectar.
  - `cortar()`/`reponer()` son la ALIMENTACIÓN virtual del PLC (sus 24 V en el tablero): el PLC
    de afuera no se reinicia con la planta, y sin tensión virtual tiene que enterarse.
  - opcionales: `escribir(ruta, valor)` (D10), `pausar()`/`reanudar()` (D8), `reconectar()`,
    `cerrar()` (la corrida lo llama al terminar, bien o mal).
  - cualquier miembro que pierde el lazo lanza `LazoCortado(motivo)`: en el lote la corrida
    termina con su hora, sin resultado parcial (D8).

Puro: stdlib. Lo importan el worker y la API.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PuertoPLC(Protocol):
    """Los 13 miembros que la corrida usa de un PLC (D4)."""

    compilado: object            # su `.entradas`: los bornes que la corrida le escribe
    estado: str                  # RUN, STOP o SIN_TENSION (`apolo.plc`)
    salidas: dict                # borne → valor, tras el último ciclo
    falla: dict | None           # la última falla ({tipo, …}) o None
    fallas: list                 # todas las fallas de la corrida
    scans: int                   # cuántos scans corrió

    def escribir_entrada(self, borne: str, valor) -> None: ...
    def paso(self, t_ms: int) -> dict: ...
    def cortar(self) -> None: ...
    def reponer(self, t_ms: int) -> None: ...
    def stop(self) -> None: ...
    def run(self, t_ms: int) -> None: ...
    def variables(self) -> dict: ...


#: Los miembros obligatorios: datos (declarados en la clase) y métodos.
DATOS = ("compilado", "estado", "salidas", "falla", "fallas", "scans")
METODOS = ("escribir_entrada", "paso", "cortar", "reponer", "stop", "run", "variables")
MIEMBROS = DATOS + METODOS
#: Los opcionales: si están, son llamables.
OPCIONALES = ("escribir", "pausar", "reanudar", "reconectar", "cerrar")


class LazoCortado(Exception):
    """El lazo con el PLC de afuera se perdió (o no se pudo abrir). `t_s` lo pone la corrida:
    la hora virtual del intercambio en que pasó."""

    def __init__(self, motivo: str, t_s: float | None = None):
        super().__init__(motivo)
        self.motivo = str(motivo)
        self.t_s = t_s

    def __str__(self) -> str:
        if self.t_s is None:
            return self.motivo
        return f"lazo cortado en t = {self.t_s:.3f} s: {self.motivo}"

    def __reduce__(self):  # se re-lanza igual en otro proceso
        return (LazoCortado, (self.motivo, self.t_s))


#: «prefijo.x» → clase del conector (los suma `apolo.extensiones`, D5).
CONECTORES: dict[str, type] = {}
#: «prefijo.x» → (extensión, versión): lo que el resultado anota en `plc_externo` (D7).
DE_EXTENSION: dict[str, tuple[str, str]] = {}


def _declarado(clase: type, nombre: str) -> bool:
    return hasattr(clase, nombre) or any(nombre in vars(c).get("__annotations__", {})
                                         for c in clase.__mro__)


def problemas_de_clase(clase) -> list[str]:
    """Lo que le falta a `clase` para ser un conector; vacío si cumple."""
    if not isinstance(clase, type):
        return [f"no es una clase sino {type(clase).__name__}"]
    out = [f"no declara «{n}»" for n in DATOS if not _declarado(clase, n)]
    out += [f"no tiene el método «{n}»" for n in METODOS if not callable(getattr(clase, n, None))]
    out += [f"«{n}» no es llamable" for n in OPCIONALES
            if hasattr(clase, n) and not callable(getattr(clase, n))]
    if not callable(getattr(clase, "validar_config", None)):
        out.append("no tiene «validar_config(config) -> list[str]»")
    return out


def registrar_conectores(clases: dict, origen: tuple[str, str]) -> None:
    """Suma los conectores de una extensión (ya validados por `extensiones_puntos`)."""
    for nombre, clase in clases.items():
        CONECTORES[nombre] = clase
        DE_EXTENSION[nombre] = origen


def cerrar(puerto) -> None:
    """`cerrar()` del conector si lo tiene; lo que lance al cerrar no tapa el motivo de antes."""
    fn = getattr(puerto, "cerrar", None)
    if callable(fn):
        try:
            fn()
        except Exception:  # noqa: BLE001, S110 — cerrar es lo último: nunca cambia el resultado
            pass


__all__ = ["CONECTORES", "DATOS", "DE_EXTENSION", "METODOS", "MIEMBROS", "OPCIONALES", "LazoCortado",
           "PuertoPLC", "cerrar", "problemas_de_clase", "registrar_conectores"]
