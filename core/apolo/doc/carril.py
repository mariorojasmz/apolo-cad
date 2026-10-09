"""El carril del log (V8.1, D1): comandos que viven en el log pero FUERA de la firma encadenada.

`_cmd_sig` (`document.py`) es un sha1 ENCADENADO: editar el comando i cambia la firma de toda la
cola y el regenerate la re-ejecuta entera. Para un comando que no hace geometría (un cable, un
dispositivo del tablero) eso es pagar segundos por editar un dato: V8.0 midió 4,9–5,2 s dentro
de la firma contra 8,5 ms fuera, en un log de 450 comandos. Un comando del CARRIL
(`CommandSpec.kind` en `KINDS_CARRIL`):

- no entra a la firma: las firmas y los checkpoints se cuentan sobre los comandos de ESCENA
  (`separar`). Editar, insertar o borrar uno del carril no corre ningún índice ni re-ejecuta
  ningún executor;
- se evalúa DESPUÉS del bucle, contra la escena y las variables FINALES (`evaluar`), y lo que
  devuelve queda en `doc.electrico`, dentro del bloque atómico del regenerate;
- es estricto en las mutaciones y tolerante en la carga, como el resto del log.

Un log SIN carril da firmas y checkpoints byte-idénticos a los de antes: no hay bump de
`GEOM_CACHE_EPOCH` ni de versiones. Un tipo que el registro no conoce es de escena, como
siempre: el regenerate lo rechaza o, en una carga, lo suprime.

Qué SIGNIFICA cada comando del carril lo decide el evaluador (`EVALUADOR`). Hasta V8.1-F3 el de
por defecto devuelve los comandos validados en el orden del log.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

from apolo.commands.errors import CommandError
from apolo.commands.registry import REGISTRY, validate_params
from apolo.doc.errors import DocumentError

KINDS_CARRIL = frozenset({"electrico"})  # `CommandSpec.kind` de los comandos del carril

#: `fallo(entrada, mensaje)`: estricto, lanza `DocumentError`; tolerante, suprime y sigue.
Fallo = Callable[[dict, Any], None]
#: `evaluador(entradas, escena, variables, fallo) -> modelo` (lo que publica `doc.electrico`).
Evaluador = Callable[[list[dict], dict, dict, Fallo], Any]


def es_carril(cmd: dict) -> bool:
    tipo = cmd.get("type")
    spec = REGISTRY.get(tipo) if isinstance(tipo, str) else None
    return spec is not None and spec.kind in KINDS_CARRIL


class Particion(NamedTuple):
    escena: list[dict]  # comandos de escena y de variables, en el orden del log
    carril: list[dict]  # comandos del carril, en el orden del log
    posiciones: list[int]  # posiciones[j] = índice en el log del j-ésimo comando de escena


def separar(commands: list[dict]) -> Particion:
    """El log partido en escena y carril. Las firmas (`_regen_sigs`) y las claves de los
    checkpoints (`_regen_ckpts`) son índices de `escena`, no del log."""
    escena: list[dict] = []
    carril: list[dict] = []
    posiciones: list[int] = []
    for i, cmd in enumerate(commands):
        if es_carril(cmd):
            carril.append(cmd)
        else:
            escena.append(cmd)
            posiciones.append(i)
    return Particion(escena, carril, posiciones)


def n_escena(commands: list[dict]) -> int:
    """Cuántos comandos de escena tiene el log: el rango de las firmas y los checkpoints."""
    return sum(1 for cmd in commands if not es_carril(cmd))


def vacio() -> list:
    """El modelo de un documento sin carril (`doc.electrico` por defecto)."""
    return []


def ordenados(entradas: list[dict], escena: dict, variables: dict, fallo: Fallo) -> list[dict]:
    """El evaluador por defecto hasta F3: los comandos validados, en el orden del log."""
    return list(entradas)


EVALUADOR: Evaluador = ordenados  # se lee en cada `evaluar`: un test lo parchea en el módulo


def evaluar(comandos: list[dict], escena: dict, variables_raw: dict, variables: dict, *,
            tolerant: bool, suprimidos: list, evaluador: Evaluador | None = None) -> Any:
    """Evalúa el carril contra la escena y las variables FINALES y devuelve el modelo.

    Primero valida los params de cada comando con `validate_params` (los `=expr` resuelven
    contra `variables_raw`, las variables finales). Después pasa al evaluador las entradas
    `{id, type, params}` (params = el modelo pydantic resuelto), en el orden del log. Cada
    problema, de params o del evaluador, pasa por `fallo`: estricto (mutaciones) lanza
    `DocumentError` y el documento revierte; tolerante (cargas) lo anota en `suprimidos` con la
    forma de `regen_suppressed` y la entrada queda fuera. El log nunca se toca."""
    if not comandos:
        return vacio()

    def fallo(cmd: dict, error: Any) -> None:
        if not tolerant:
            raise DocumentError(f"Error al regenerar {cmd['id']} ({cmd['type']}): {error}")
        suprimidos.append({"command_id": cmd["id"], "type": cmd["type"], "error": str(error)})

    entradas: list[dict] = []
    for cmd in comandos:
        try:
            modelo = validate_params(cmd["type"], cmd["params"], variables_raw)
        except CommandError as exc:
            fallo(cmd, exc)
            continue
        entradas.append({"id": cmd["id"], "type": cmd["type"], "params": modelo})
    return (evaluador or EVALUADOR)(entradas, escena, variables, fallo)
