"""Exportación a formatos de intercambio."""

from __future__ import annotations

from build123d import Compound, export_step


def export_step_file(shapes: list, path: str) -> None:
    if not shapes:
        raise ValueError("No hay sólidos visibles que exportar")
    target = shapes[0] if len(shapes) == 1 else Compound(children=list(shapes))
    export_step(target, path)
