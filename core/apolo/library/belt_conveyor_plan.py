"""El PLAN de `create_belt_conveyor` (v4): piezas, uniones declaradas y anclajes a tierra.

Puro respecto del documento: formas build123d y tuplas. El executor (`commands/exec_faja.py`)
emite cada pieza como `{cmd}_{sufijo}` y corre `fasten`/`ground` con las uniones del plan: lo
que la plantilla toca entre sus piezas queda DECLARADO por ella (nunca por una lista blanca).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from build123d import Box, Cylinder, Pos, Rotation

from apolo.kernel.shapes import place

from .conveyor import ConveyorPart


@dataclass
class PiezaFaja(ConveyorPart):
    material: str | None = None  # explícito: la heurística del nombre no decide («larguero»)


@dataclass
class Plan:
    piezas: list[PiezaFaja] = field(default_factory=list)
    #: (sufijo, pieza a, pieza b, kind, nota, dimensiones) — sufijos de pieza, sin el cmd_id
    uniones: list[tuple] = field(default_factory=list)
    #: (sufijo, pieza, nota)
    anclajes: list[tuple] = field(default_factory=list)
    #: cuentas con que la plantilla decidió una geometría (F1b: «base_motor»), para leerlas
    calculos: dict = field(default_factory=dict)

    def pieza(self, suf: str, nombre: str, base, *, comp: str | None = None,
              cut: float | None = None, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0),
              key: str | None = None, material: str | None = None) -> str:
        """`base` en su marco local (instanciable con `key`) o ya en el mundo (sin `key`)."""
        self.piezas.append(PiezaFaja(
            suf, nombre, place(base, pos, rot), comp, cut, base_key=key,
            base_shape=base if key else None, position=tuple(pos), rotation=tuple(rot),
            material=material))
        return suf

    def union(self, suf: str, a: str, b: str, kind: str, nota: str, **dim) -> None:
        self.uniones.append((suf, a, b, kind, nota, dim))

    def anclaje(self, suf: str, pieza: str, nota: str) -> None:
        self.anclajes.append((suf, pieza, nota))


def caja(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float):
    """Caja alineada a los ejes por sus límites (en cualquier orden)."""
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return Pos((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0) * Box(x1 - x0, y1 - y0, z1 - z0)


def cilindro_y(x: float, z: float, y0: float, y1: float, r: float):
    """Cilindro de eje Y entre `y0` y `y1` (en cualquier orden)."""
    y0, y1 = sorted((y0, y1))
    return Pos(x, (y0 + y1) / 2.0, z) * Rotation(90, 0, 0) * Cylinder(r, y1 - y0)


def ranura_x(x: float, z: float, y0: float, y1: float, largo: float, alto: float):
    """Ranura de puntas redondas a lo largo de X (eje Y): `largo` total, `alto` = su ancho."""
    y0, y1 = sorted((y0, y1))
    recto = largo - alto
    out = caja(x - recto / 2.0, x + recto / 2.0, y0, y1, z - alto / 2.0, z + alto / 2.0)
    for sx in (-1.0, 1.0):
        out = out + cilindro_y(x + sx * recto / 2.0, z, y0, y1, alto / 2.0)
    return out
