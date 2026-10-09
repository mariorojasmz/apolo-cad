"""Sensores de la simulación dinámica (V8.2 D8): fotoceldas por rayo.

Cada sensor es un rayo `mj_ray` con `flg_static=0`: ignora lo estático (bastidor, banda,
piso) y ve todo lo que se mueve —productos y cuerpos de junta—, como una fotocelda montada en
la máquina que no se ve a sí misma. V8.0 midió 2,2 µs por rayo: se evalúa en CADA
intercambio y reporta FLANCOS con su tiempo (y qué los causó) más el estado muestreado a
los fotogramas. MuJoCo sobre datos: corre bajo `PHYSICS_LOCK`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MM = 0.001


@dataclass
class SensorDatos:
    nombre: str
    origen: tuple        # m
    direccion: tuple     # unitario
    alcance: float       # m


class Fotoceldas:
    def __init__(self, mujoco, m, sensores: list, nombre_cuerpo: dict):
        self.mj, self.m = mujoco, m
        self.sensores = sensores
        self.nombre_cuerpo = nombre_cuerpo   # body id → nombre legible
        self.pnt = [np.asarray(s.origen, float) for s in sensores]
        self.vec = [np.asarray(s.direccion, float) for s in sensores]
        self.gid = np.array([-1], dtype=np.int32)
        self.estado = [False] * len(sensores)
        self.objeto: list[str | None] = [None] * len(sensores)
        self.flancos: list[list[dict]] = [[] for _ in sensores]
        self.muestras: list[list[list]] = [[] for _ in sensores]

    def medir(self, d, t: float) -> None:
        """Evalúa los rayos en el instante `t` y registra los flancos."""
        for k, s in enumerate(self.sensores):
            dist = self.mj.mj_ray(self.m, d, self.pnt[k], self.vec[k], None, 0, -1, self.gid)
            on = 0.0 <= dist <= s.alcance
            obj = None
            if on and self.gid[0] >= 0:
                obj = self.nombre_cuerpo.get(int(self.m.geom_bodyid[self.gid[0]]))
            if on != self.estado[k]:
                self.flancos[k].append({"t": round(t, 4), "tipo": "sube" if on else "baja",
                                        "objeto": obj if on else self.objeto[k]})
            self.estado[k] = on
            self.objeto[k] = obj

    def muestrear(self, t: float) -> None:
        for k in range(len(self.sensores)):
            self.muestras[k].append([round(t, 4), int(self.estado[k])])

    def salida(self) -> dict:
        return {
            s.nombre: {
                "tipo": "rayo",
                "origen_mm": [round(c / MM, 2) for c in s.origen],
                "direccion": [round(c, 4) for c in s.direccion],
                "alcance_mm": round(s.alcance / MM, 1),
                "flancos": self.flancos[k],
                "cuentas": sum(1 for f in self.flancos[k] if f["tipo"] == "sube"),
                "muestras": self.muestras[k],
            }
            for k, s in enumerate(self.sensores)
        }
