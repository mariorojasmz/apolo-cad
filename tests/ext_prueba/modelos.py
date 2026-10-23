"""El modelo de co-simulación de la extensión falsa: una lámpara que se enciende con tensión."""

from __future__ import annotations

from apolo.extensiones_api import Modelo


class Lampara(Modelo):
    tipo = "prueba.lampara"

    def __init__(self, p) -> None:
        super().__init__(p)
        self.encendida = False

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        self.encendida = bool((entradas or {}).get("U_V"))
        return self.salidas()

    def salidas(self) -> dict:
        return {"encendida": self.encendida}
