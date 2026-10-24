"""Reglas de la puerta de ENTREGA que suma una extensión (`Extension.entrega`; plan
puntos-de-extension-entregables, D3). Puro: guarda lo declarado y valida lo que da cada regla;
quien llama a `ReglaEntrega.evaluar(doc)` es `services/delivery_inputs.py`, bajo el lock del
llamador, y quien las pone en el semáforo, `library/delivery.py`.

`evaluar(doc)` da `None` (no aplica a este documento: no aparece) o una lista de hallazgos
`{estado: ok | aviso | error, detalle[, piezas]}`. Sin extensiones con reglas, `DE_EXTENSION`
está vacío y la puerta da exactamente lo de siempre.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

ORIGEN = "extension:"
ESTADOS = ("ok", "aviso", "error")


@dataclass(frozen=True)
class ReglaEntrega:
    """Una regla de la puerta de entrega: `id` «prefijo.x», `titulo` (lo que lee la persona en
    `regla`) y `evaluar(doc)` → None | [{estado, detalle, piezas?}]."""

    id: str
    titulo: str
    evaluar: Callable


#: nombre de la extensión → (version_entrega, (ReglaEntrega, …)); lo llena `extensiones.cargar`.
DE_EXTENSION: dict[str, tuple[int, tuple[ReglaEntrega, ...]]] = {}


def vigentes() -> list[tuple[str, ReglaEntrega]]:
    return [(nombre, r) for nombre, (_v, reglas) in DE_EXTENSION.items() for r in reglas]


def version() -> str:
    """«+nombre.version_entrega» por cada extensión con reglas (vacío sin ninguna)."""
    return "".join(f"+{nombre}.{v}" for nombre, (v, _r) in DE_EXTENSION.items())


def hallazgos(salida) -> list[dict] | None:
    """Los hallazgos validados de lo que dio `evaluar`, o `ValueError` con el motivo."""
    if salida is None:
        return None
    if not isinstance(salida, (list, tuple)):
        raise ValueError(f"da None o una lista de hallazgos, no {type(salida).__name__}")
    out = []
    for h in salida:
        if not isinstance(h, dict) or h.get("estado") not in ESTADOS:
            raise ValueError(f"un hallazgo es {{estado: {' | '.join(ESTADOS)}, detalle, "
                             f"piezas?}}, no {h!r}"[:300])
        if not isinstance(h.get("detalle", ""), str):
            raise ValueError("`detalle` de un hallazgo es texto")
        piezas = h.get("piezas") or []
        if not isinstance(piezas, (list, tuple)) or not all(isinstance(p, str) for p in piezas):
            raise ValueError("`piezas` de un hallazgo es una lista de ids")
        out.append({"estado": h["estado"], "detalle": h.get("detalle", ""), "piezas": list(piezas)})
    return out
