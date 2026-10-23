"""El lado del padre de una sesión EN VIVO (plan V8.4 D1–D2): el worker en su proceso.

`ProcesoVivo(snap, config, al_mensaje)` lanza `python -m apolo.cosim.worker` con
`subprocess.Popen` (como el lote: nada de `multiprocessing`) y BLAS de un hilo, le manda
`V` + la configuración y el snapshot, y entrega cada frame del hijo a `al_mensaje(etiqueta,
cuerpo)` desde un hilo lector (`J` JSON, `F` fotograma, `E` error); al terminar el hijo llama
`al_mensaje(None, código)`. `enviar(msg)` escribe una acción (`A` + JSON). `cerrar()` cierra
stdin (el hijo lo lee como «parar» y manda su `fin`), espera y, si no sale, lo mata: una sesión
cerrada no deja procesos huérfanos.

No toma `STATE_LOCK`, `PHYSICS_LOCK` ni `COSIM_LOCK`: el snapshot ya se tomó y la sesión viva
convive con una corrida por lote. No importa `apolo.state` ni la API.
"""

from __future__ import annotations

import collections
import json
import os
import pickle
import struct
import subprocess
import sys
import threading

from .proceso import BLAS_UN_HILO, CosimError
from .worker import read_frame

ESPERA_CIERRE_S = 3.0


def _frame(body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + body


class ProcesoVivo:
    def __init__(self, snap, config: dict, al_mensaje):
        self.al_mensaje = al_mensaje
        cmd = [sys.executable] + (["-B"] if sys.flags.dont_write_bytecode else []) + ["-m", "apolo.cosim.worker"]
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, env={**os.environ, **BLAS_UN_HILO})
        except OSError as exc:
            raise CosimError(f"el worker de la sesión en vivo no pudo arrancar: {exc}") from exc
        self._escribir = threading.Lock()
        self.stderr: collections.deque = collections.deque(maxlen=40)
        self.listo: dict | None = None
        threading.Thread(target=self._leer_err, daemon=True).start()
        self._enviar_crudo(b"V" + json.dumps(config).encode("utf-8"))
        self._enviar_crudo(pickle.dumps(snap, protocol=pickle.HIGHEST_PROTOCOL))
        threading.Thread(target=self._leer, daemon=True).start()

    @property
    def pid(self) -> int:
        return self.proc.pid

    @property
    def vivo(self) -> bool:
        return self.proc.poll() is None

    def _enviar_crudo(self, body: bytes) -> bool:
        with self._escribir:
            try:
                self.proc.stdin.write(_frame(body))
                self.proc.stdin.flush()
                return True
            except (OSError, ValueError):
                return False

    def enviar(self, msg: dict) -> bool:
        """Una acción, un evento o un control al worker. False si ya no escucha."""
        return self._enviar_crudo(b"A" + json.dumps(msg, ensure_ascii=False).encode("utf-8"))

    def _leer_err(self) -> None:
        for linea in iter(self.proc.stderr.readline, b""):
            self.stderr.append(linea.decode("utf-8", "replace").rstrip())

    def _leer(self) -> None:
        out = self.proc.stdout
        try:
            while True:
                cuerpo = read_frame(out)
                if cuerpo is None:
                    break
                etiqueta, resto = cuerpo[:1], cuerpo[1:]
                if etiqueta == b"R":
                    self.listo = json.loads(resto.decode("utf-8"))
                    continue
                self.al_mensaje(etiqueta, resto)
        finally:
            codigo = self.proc.wait()
            self.al_mensaje(None, codigo)

    def cola_stderr(self) -> str:
        return "\n".join(list(self.stderr)[-8:])

    def cerrar(self, espera_s: float = ESPERA_CIERRE_S) -> None:
        """Cierra stdin (= «parar»), espera a que salga y, si no, lo mata. Idempotente."""
        with self._escribir:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
        try:
            self.proc.wait(timeout=espera_s)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()

    def matar(self) -> None:
        """Lo mata sin esperar (el hilo lector recoge su salida y avisa con `(None, código)`)."""
        if self.vivo:
            try:
                self.proc.kill()
            except OSError:
                pass

    def cerrar_en_hilo(self) -> threading.Thread:
        """`cerrar` sin bloquear a quien llama (el loop del WebSocket, que puede estar cancelado)."""
        hilo = threading.Thread(target=self.cerrar, daemon=True, name=f"cerrar-vivo-{self.pid}")
        hilo.start()
        return hilo
