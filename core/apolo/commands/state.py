"""Estado de regeneración CON NOMBRE: lo que el regenerate pasa de comando en comando.

Reemplaza a la 8-tupla posicional `(scene, variables, joints, mates, constraints, fasteners,
grounds, groups)` (plan `estado-regen-y-params-estrictos`, D2): los ocho son dicts del mismo
tipo, así que cruzar dos al desarmar una tupla no lanzaba nada y daba geometría equivocada.
Con nombres, un typo es un `AttributeError` (`slots`: tampoco se puede inventar un campo).

Vive en `commands/` y no en `doc/` porque `doc/document.py` importa `commands.registry`
(al revés sería un import circular).

SEGURIDAD de los checkpoints: `copy()` es el puerto 1:1 del viejo `_copy_state`. Las
Features se copian SUPERFICIALMENTE (el shape OCCT se COMPARTE: ningún executor muta un shape
in-place, así un checkpoint no copia geometría) y el resto se aísla por copia (los executors
mutan juntas y restricciones en sitio, p. ej. `transform_group`).

La caché de geometría guarda el estado POR NOMBRE (`to_plain`/`from_plain`), nunca la clase
picklada: mover o renombrar la clase no rompe blobs viejos; cambiar sus CAMPOS sí cambia el
formato → bump de `GEOM_CACHE_EPOCH` (`doc/geomcache.py`).

`ExecContext` es lo que recibe un executor (D3): el estado VIVO y los adjuntos del documento.
"""

from __future__ import annotations

import copy as _copy
from dataclasses import dataclass, field, fields
from typing import Any

from .expressions import resolve_all


@dataclass(slots=True)
class RegenState:
    """Estado del documento tras ejecutar un prefijo del log (checkpoint del regenerate)."""

    scene: dict[str, Any] = field(default_factory=dict)  # feature_id → Feature
    variables: dict[str, str] = field(default_factory=dict)  # nombre → expresión cruda
    joints: dict[str, dict] = field(default_factory=dict)
    mates: dict[str, dict] = field(default_factory=dict)
    constraints: dict[str, dict] = field(default_factory=dict)  # restricciones de riel / N-GDL
    fasteners: dict[str, dict] = field(default_factory=dict)
    grounds: dict[str, dict] = field(default_factory=dict)
    groups: dict[str, dict] = field(default_factory=dict)

    def copy(self) -> RegenState:
        """Copia AISLADA: Features por shallow-copy (shape compartido), variables por
        `dict()`, el resto por `deepcopy` — lo mismo que hacía `_copy_state`."""
        return RegenState(
            scene={fid: _copy.copy(f) for fid, f in self.scene.items()},
            variables=dict(self.variables),
            joints=_copy.deepcopy(self.joints),
            mates=_copy.deepcopy(self.mates),
            constraints=_copy.deepcopy(self.constraints),
            fasteners=_copy.deepcopy(self.fasteners),
            grounds=_copy.deepcopy(self.grounds),
            groups=_copy.deepcopy(self.groups),
        )

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(f.name for f in fields(cls))

    def to_plain(self) -> dict[str, dict]:
        """Dict por NOMBRE de campo (los mismos objetos, sin copiar) para serializar."""
        return {name: getattr(self, name) for name in self.field_names()}

    @classmethod
    def from_plain(cls, data: Any) -> RegenState:
        """Inverso de `to_plain`. Exige EXACTAMENTE los campos de hoy, todos dicts: un blob
        de otro formato lanza `ValueError` (el caller lo trata como caché inservible)."""
        names = cls.field_names()
        if not isinstance(data, dict) or set(data) != set(names):
            raise ValueError("el estado no tiene los campos de RegenState")
        if not all(isinstance(data[n], dict) for n in names):
            raise ValueError("cada campo de RegenState debe ser un dict")
        return cls(**{n: data[n] for n in names})


@dataclass(frozen=True, slots=True)
class ExecContext:
    """Lo que un executor recibe además de `cmd_id` y sus params: `executor(ctx, cmd_id, p)`.

    Una sola forma de llamada para los 53 executors (plan estado-regen, D3): antes la firma
    la elegían 8 flags `wants_*` con 11 formas distintas. Los dicts son los VIVOS del estado
    (el executor los muta en sitio, como siempre); agregar contexto = una propiedad aquí, no
    un flag nuevo ni una rama en el despacho."""

    state: RegenState
    attachments: dict[str, bytes] = field(default_factory=dict)  # adjuntos (STEP, .apolo)

    @property
    def scene(self) -> dict[str, Any]:
        return self.state.scene

    @property
    def variables(self) -> dict[str, str]:
        """Las expresiones CRUDAS (`set_variable` escribe aquí)."""
        return self.state.variables

    @property
    def joints(self) -> dict[str, dict]:
        return self.state.joints

    @property
    def mates(self) -> dict[str, dict]:
        return self.state.mates

    @property
    def constraints(self) -> dict[str, dict]:
        return self.state.constraints

    @property
    def fasteners(self) -> dict[str, dict]:
        return self.state.fasteners

    @property
    def grounds(self) -> dict[str, dict]:
        return self.state.grounds

    @property
    def groups(self) -> dict[str, dict]:
        return self.state.groups

    def resolved_variables(self) -> dict[str, float]:
        """Las variables EVALUADAS en este punto del log (lo que ve `run_script` como `V`)."""
        return resolve_all(self.state.variables)
