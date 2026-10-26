"""El estado que comparten los bloques de `conveyor_engineering_check` (plan
partir-nucleo-congelado-ii, F3, D4): los argumentos, los locales del preámbulo y lo que un bloque
produce para otro. Un campo es un local de la función original con el MISMO nombre; nada se
deriva aquí (sin `__post_init__`): el orquestador de `rules.py` lo llena y cada bloque lo lee.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ContextoFaja:
    # argumentos de `conveyor_engineering_check`
    conveyor: dict
    carga_kg: float
    largo_paquete_mm: float
    velocidad_m_s: float
    ancho_paquete_mm: float | None
    # locales del preámbulo (`checks` es LA lista que se devuelve: los bloques le agregan)
    checks: list[dict]
    largo: float
    ancho: float
    paso: float
    rodillo_ref: str
    motor_ref: str
    tipo: str
    tambor_d: Any
    rpm_motor: Any
    torque_nm: Any
    altura: Any
    rodillo: Any  # el `Component` de catálogo del rodillo
    v_real: float | None
    v_eff: float
    # lo que produce un bloque para los siguientes (lo asigna el orquestador con su `return`)
    support_count: int | None = None   # 1 · apoyo del paquete → 2
    soporte: str | None = None         # 4 · arrastre → motorización
    metodo_norma: str | None = None    # 4 · arrastre → motorización
    pull_n: float | None = None        # 4 · arrastre → motorización, 5, 5c, 9
    p_req: float | None = None         # 4 · arrastre → motorización
    frame: dict | None = None          # 8 · flecha del bastidor → 9
