"""La `Entrada` del registro de la puerta de publicación y sus predicados `aplica_si` (`siempre`,
`hecho`, `hay`, `hay_alguno`). Puro. Viven aparte para que un ítem pueda declarar su `Entrada`
junto a su control (`nombres.ENTRADA`, plan nombres-por-funcion A3) sin importar `registro.py`,
que los re-exporta por identidad.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

Predicado = Callable[[dict], "tuple[bool, str]"]


def siempre(_hechos: dict) -> tuple[bool, str]:
    return True, ""


def hecho(clave: str, porque: str) -> Predicado:
    """Aplica si el hecho `clave` del modelo es verdadero; si no, NO_APLICA con `porque`."""
    def predicado(hechos: dict) -> tuple[bool, str]:
        return bool(hechos.get(clave)), porque
    predicado.__name__ = f"hecho_{clave}"
    return predicado


def hay(tipo: str, porque: str) -> Predicado:
    """Aplica si el modelo tiene ELEMENTOS de `tipo` (`hechos["elementos"][tipo]`, {clase: n})."""
    def predicado(hechos: dict) -> tuple[bool, str]:
        return sum((hechos.get("elementos") or {}).get(tipo, {}).values()) > 0, porque
    predicado.__name__ = f"hay_{tipo}"
    return predicado


def hay_alguno(tipos: tuple, porque: str) -> Predicado:
    """Aplica si el modelo tiene elementos de ALGUNO de los `tipos`."""
    def predicado(hechos: dict) -> tuple[bool, str]:
        return any(hay(t, porque)(hechos)[0] for t in tipos), porque
    predicado.__name__ = "hay_" + "_o_".join(tipos)
    return predicado


@dataclass(frozen=True)
class Entrada:
    id: str
    titulo: str
    modo_de_falla: str
    norma: str
    familia: str
    aplica_si: Predicado
    evaluar: Callable[[dict], dict]  # insumos → {estado, detalle, evidencia, piezas}
    elementos: str = ""              # tipo de `hechos["elementos"]` que la evidencia nombra
