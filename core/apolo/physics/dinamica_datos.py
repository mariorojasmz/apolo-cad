"""El snapshot PURO de la dinámica (V8.2): lo que `prepare_dynamics` hornea bajo `STATE_LOCK`.

Vive aparte de `dinamica.py` (que importa OCCT para la preparación) porque viaja en pickle al
worker de la co-simulación (V8.3 D11) y allí se des-serializa sin cargar la geometría.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DynamicsSnapshot:
    xml: str | None
    duracion_s: float
    timestep: float
    nstep: int
    fps: int
    gravedad: float
    modelo_banda: str = "contacto"
    cuerpos: list = field(default_factory=list)     # [{name, junta, tipo, piezas, origen_mm}]
    juntas: dict = field(default_factory=dict)      # apolo → {mj, tipo, rango}
    piezas: list = field(default_factory=list)      # animador de gravedad
    productos: list = field(default_factory=list)   # animador de caída + estado inicial
    motores: list = field(default_factory=list)
    bandas: list = field(default_factory=list)
    sensores: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    early: dict | None = None
    sumideros: list = field(default_factory=list)   # [(punto_m, normal)]: retiran productos
    #: el balance de producto (plan balance-de-producto D5): {plazo_s, quieto_s, zonas_espera,
    #: sumideros: [nombres]}; None = no se rastrea (la salida de siempre)
    flujo: dict | None = None
    #: plan motor-a-eje-lineal F4: {junta: q0 (m | rad)} donde ARRANCA cada junta que lo declara;
    #: vacío = todas en la pose de diseño (el MJCF es siempre el de la pose de diseño)
    inicial: dict = field(default_factory=dict)
