"""Un PLC FALSO en otro proceso (D15 de plc-en-el-lazo): `apolo.plc.PLC` con el reloj de PARED
detrás de un servidor TCP de JSON por línea (el otro lado de `conector_plc.ConectorTCP`).

    python -B -m ext_prueba.plc_falso <fuente.st> [--ciclo 10] [--avisar N] [--puerto P]

Imprime `PUERTO <n>` cuando escucha (127.0.0.1, puerto libre o `--puerto`: así «vuelve» al mismo
puerto tras matarlo) y, con `--avisar`, `PASOS <N>` al atender el paso N (así un test lo mata a
mitad de un lote); `OP pausar` / `OP reanudar` cuando el conector se los pide (la pausa de la
sesión en vivo: un PLC de verdad no se detiene, sólo se entera). Como un PLC real, NO se reinicia
con la planta: su memoria sobrevive entre conexiones. Sale solo cuando se cierra su stdin (el
test que lo lanzó terminó o murió): nunca queda huérfano.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

from apolo.plc import PLC, compilar


def _vigilar_stdin() -> None:
    sys.stdin.buffer.read()  # hasta EOF
    os._exit(0)


def _estado(plc: PLC) -> dict:
    return {"estado": plc.estado, "salidas": plc.salidas, "falla": plc.falla, "fallas": plc.fallas,
            "scans": plc.scans, "variables": plc.variables()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fuente")
    ap.add_argument("--ciclo", type=int, default=10)
    ap.add_argument("--avisar", type=int, default=0)
    ap.add_argument("--puerto", type=int, default=0)
    a = ap.parse_args()
    plc = PLC(compilar(Path(a.fuente).read_text(encoding="utf-8")), ciclo_ms=a.ciclo)
    t0 = time.perf_counter()

    def ahora_ms() -> int:  # el reloj de PARED: por eso no es determinista
        return int((time.perf_counter() - t0) * 1000)

    srv = socket.create_server(("127.0.0.1", a.puerto))
    threading.Thread(target=_vigilar_stdin, daemon=True).start()
    print(f"PUERTO {srv.getsockname()[1]}", flush=True)
    pasos = 0
    while True:
        con, _ = srv.accept()
        con.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with con, con.makefile("rwb") as f:
            try:
                for linea in f:
                    msg = json.loads(linea)
                    op = msg["op"]
                    if op == "paso":
                        for borne, valor in msg["entradas"].items():
                            plc.escribir_entrada(borne, valor)
                        plc.paso(ahora_ms())
                        pasos += 1
                        if pasos == a.avisar:
                            print(f"PASOS {pasos}", flush=True)
                    elif op == "cortar":
                        plc.cortar()
                    elif op == "reponer":
                        plc.reponer(ahora_ms())
                    elif op == "stop":
                        plc.stop()
                    elif op == "run":
                        plc.run(ahora_ms())
                    elif op in ("pausar", "reanudar"):
                        print(f"OP {op}", flush=True)
                    f.write(json.dumps(_estado(plc)).encode("utf-8") + b"\n")
                    f.flush()
            except OSError:
                pass  # el cliente se fue: espera al próximo


if __name__ == "__main__":
    sys.exit(main())
