"""Un suscriptor del bus de la sesión viva (plan plc-en-el-lazo D11, D15): lo que haría en proceso
una pantalla de operador o un SCADA. Sigue la sesión con `suscribir` desde un hilo propio (todo lo
que llega queda en orden en `orden`, `jsons` y `fotogramas`) y le manda acciones con
`enviar_vivo`. Sólo usa `apolo.extensiones_api`, como una extensión de verdad.
"""

from __future__ import annotations

import threading
import time

from apolo.extensiones_api import enviar_vivo, suscribir

NOMBRE = "prueba.scada"


class SuscriptorPrueba:
    def __init__(self, nombre: str = NOMBRE, max_fotogramas: int = 60):
        self.nombre = nombre
        self.sub = suscribir(nombre, max_fotogramas)
        self.orden: list[str] = []          # el `tipo` de cada JSON; «F» por cada fotograma
        self.jsons: list[dict] = []
        self.fotogramas: list[bytes] = []
        self._cv = threading.Condition()
        self._hilo = threading.Thread(target=self._leer, daemon=True, name=f"suscriptor-{nombre}")
        self._hilo.start()

    def _leer(self) -> None:
        while True:
            m = self.sub.recibir()
            if m is None:   # cerrada
                return
            with self._cv:
                if isinstance(m, bytes):
                    self.fotogramas.append(m)
                    self.orden.append("F")
                else:
                    self.jsons.append(m)
                    self.orden.append(m["tipo"])
                self._cv.notify_all()

    def esperar(self, pred, timeout: float = 60.0) -> dict:
        """El primer JSON que cumple `pred`; `AssertionError` si no llega en `timeout` s."""
        hasta = time.monotonic() + timeout
        with self._cv:
            while True:
                hallado = next((m for m in self.jsons if pred(m)), None)
                if hallado is not None:
                    return hallado
                falta = hasta - time.monotonic()
                if falta <= 0:
                    raise AssertionError(f"{self.nombre}: no llegó (recibido: {self.orden[-20:]})")
                self._cv.wait(falta)

    def enviar(self, msg) -> bool:
        return enviar_vivo(self.nombre, msg)

    def cerrar(self) -> None:
        self.sub.cerrar()
        self._hilo.join(5)
