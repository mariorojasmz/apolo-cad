"""Ensamblaje: relaciones de mate persistentes entre piezas."""

from .mates import MateError, register_mate, solve_mates

__all__ = ["MateError", "register_mate", "solve_mates"]
