"""Física de cuerpos rígidos (gravedad, drop-test) vía MuJoCo (motor aparte de OCCT).

PyBullet no tiene wheel para Python 3.13 (requiere compilar); MuJoCo (Apache) sí, así
que es el motor embebido. Solo `sim.py` lo importa, de forma perezosa.
"""

from .sim import PhysicsError, drop_test, prepare_drop, simulate_drop

__all__ = ["PhysicsError", "drop_test", "prepare_drop", "simulate_drop"]
