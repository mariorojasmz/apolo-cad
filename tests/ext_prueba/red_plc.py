"""La «librería de red» del conector falso: JSON por línea sobre TCP de stdlib.

La importa `conector_plc` AL CONECTAR, nunca al importarse (D5 de plc-en-el-lazo): el worker de
la co-simulación des-serializa el conector por pickle y no debe cargar la red de una extensión
hasta usarla. `test_cosim_plc_externo.py` lo vigila con este módulo.
"""

from __future__ import annotations

import json
import socket


class Linea:
    """Un pedido, una respuesta: cada mensaje es un objeto JSON en una línea."""

    def __init__(self, host: str, puerto: int, timeout_s: float):
        self._s = socket.create_connection((host, puerto), timeout=timeout_s)
        self._s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # sin Nagle: ida y vuelta corta
        self._f = self._s.makefile("rwb")

    def pedir(self, msg: dict) -> dict | None:
        """La respuesta, o None si el otro lado cerró. `OSError` si se cortó o no contestó."""
        self._f.write(json.dumps(msg).encode("utf-8") + b"\n")
        self._f.flush()
        linea = self._f.readline()
        return json.loads(linea) if linea else None

    def cerrar(self) -> None:
        for x in (self._f, self._s):
            try:
                x.close()
            except OSError:
                pass


def abrir(host: str, puerto: int, timeout_s: float) -> Linea:
    return Linea(host, puerto, timeout_s)
