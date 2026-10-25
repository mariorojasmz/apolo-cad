"""Un suscriptor del bus de la sesión viva (plan plc-en-el-lazo D11, D15): lo que haría en proceso
una pantalla de operador o un SCADA. Sigue la sesión con `suscribir` desde un hilo propio (todo lo
que llega queda en orden en `orden`, `jsons` y `fotogramas`) y le manda acciones con
`enviar_vivo`. Sólo usa `apolo.extensiones_api` (y el lector del fotograma de `MODULOS`), como una
extensión de verdad.

Llega cuando sea (pedidos-de-extensiones D11, D13): con la sesión ya abierta, lo primero es el
`inicio` (`tarde: true`), las `senales` que salieron y los `textos` acumulados. Con eso arma la
tabla (`senales`, `textos`, `variables` de cada PLC) y lee cada fotograma con la tabla de ESE
momento (`leidos`: {t, valores} por nombre; `ns` del fotograma = largo de la tabla, o `desfasados`).
"""

from __future__ import annotations

import math
import threading
import time

from apolo.extensiones_api import enviar_vivo, suscribir

NOMBRE = "prueba.scada"


class SuscriptorPrueba:
    def __init__(self, nombre: str = NOMBRE, max_fotogramas: int = 60):
        self.nombre = nombre
        self.orden: list[str] = []          # el `tipo` de cada JSON; «F» por cada fotograma
        self.jsons: list[dict] = []
        self.fotogramas: list[bytes] = []
        self.senales: list[str] = []        # la tabla: `inicio.senales` + las `senales` que llegan
        self.textos: dict = {}              # el último valor de cada señal de texto
        self.variables: dict = {}           # «-K1.Main.cuenta» → {tipo, escribible} (`inicio.plcs`)
        self.tarde = False                  # llegó con la sesión ya abierta
        self.leidos: list[dict] = []        # cada fotograma leído con la tabla de su momento
        self.desfasados = 0                 # fotogramas con otro número de señales que la tabla
        self._cv = threading.Condition()
        self.sub = suscribir(nombre, max_fotogramas)
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
                    self._leer_fotograma(m)
                else:
                    self.jsons.append(m)
                    self.orden.append(m["tipo"])
                    self._tabla(m)
                self._cv.notify_all()

    def _tabla(self, m: dict) -> None:
        if m["tipo"] == "inicio":
            self.senales, self.textos, self.tarde = list(m["senales"]), {}, bool(m.get("tarde"))
            self.variables = {f"{p['designacion']}.{v['ruta']}": {"tipo": v["tipo"], "escribible": v["escribible"]}
                              for p in m.get("plcs", ()) for v in p["variables"]}
        elif m["tipo"] == "senales":
            self.senales[m["desde"]:] = m["nombres"]
        elif m["tipo"] == "textos":
            self.textos.update(m["valores"])

    def _leer_fotograma(self, datos: bytes) -> None:
        from apolo.cosim.vivo_fotograma import FORMATO, leer_fotograma

        f = leer_fotograma(datos)
        if f["formato"] != FORMATO or len(f["senales"]) != len(self.senales):
            self.desfasados += 1
            return
        self.leidos.append({"t": f["t"], "valores": {n: float(v) for n, v in zip(self.senales, f["senales"])
                                                     if not math.isnan(float(v))}})

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
