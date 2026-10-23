"""El modo `vivo` del worker de la co-simulación (plan V8.4 D1): el reloj que espera a la pared.

`worker.py` entra aquí cuando el primer frame del padre es `V` + JSON (la configuración) y el
segundo el `CosimSnapshot`. Cada VENTANA (1/30 s de pared × `ritmo`):
  1. toma las acciones que juntó el hilo lector (`get_nowait`, nunca un `wait(timeout)`: en
     Windows redondea al tick de 15,6 ms, F0) y las agenda para el intercambio que sigue;
  2. avanza el tiempo virtual hasta el objetivo de la ventana, de a 2 ms (`Vivo.avanzar`);
  3. publica acks y rechazos, las señales nuevas, los textos que cambiaron y el fotograma;
  4. duerme lo que le sobre con `time.sleep` en tajadas cortas, mirando si llegó «parar».
Si no alcanza, sigue más lento: el factor medido viaja en cada fotograma y un aviso sale al
cruzar el umbral; una deuda de más de `REBASE_S` se perdona (no corre a recuperarla a saltos).
Con `ritmo = 0` no duerme (los tests y la medición del factor sin dormir).

PROTOCOLO (además del `R` de listo de `worker.py`):
  padre → hijo  `A` + JSON   una acción, un evento o un control (`vivo.leer_mensaje`); EOF = parar
  hijo → padre  `J` + JSON   {"tipo": "tabla", …} una vez, antes del primer fotograma
                             (`vivo_fotograma.Fotograma.tabla`); después ack, rechazo, senales,
                             textos, factor, pausa, reanudar y fin (con la grabación)
                `F` + bytes  un fotograma float32 (formato en `vivo_fotograma.py`)
                `E` + texto  el error que tumbó la sesión
"""

from __future__ import annotations

import collections
import json
import queue
import threading
import time

from .vivo import VENTANA_S, Vivo, leer_mensaje
from .worker import read_frame, write_frame

TAJADA_S = 0.004                 # dormir de a 4 ms (time.sleep de 2 ms dura 2,2 en Windows, F0)
REBASE_S = 0.25                  # deuda que se perdona de una
UMBRAL_LENTO = 0.95              # factor/ritmo bajo esto = «más lento que la pared»
VENTANAS_FACTOR = 30             # ~1 s de ventanas para medir el factor


def _lector(entrada, cola: queue.Queue) -> None:
    """Hilo lector: cada frame `A` del padre a la cola; EOF (el padre cerró) = parar."""
    while True:
        cuerpo = read_frame(entrada)
        if cuerpo is None:
            cola.put({"control": "parar", "_eof": True})
            return
        if cuerpo[:1] != b"A":
            continue
        try:
            cola.put(json.loads(cuerpo[1:].decode("utf-8")))
        except ValueError:
            cola.put({"_invalido": True})


class _Salida:
    """Lo que sale al padre. Hasta la tabla, los JSON esperan: la tabla va SIEMPRE primero."""

    def __init__(self, stream):
        self.s = stream
        self.previos: list[dict] | None = []

    def json(self, msg: dict) -> None:
        if self.previos is not None:
            self.previos.append(msg)
            return
        write_frame(self.s, b"J" + json.dumps(msg, default=str, ensure_ascii=False).encode("utf-8"))

    def abrir(self, tabla: dict) -> None:
        previos, self.previos = self.previos or [], None
        for msg in [tabla, *previos]:
            self.json(msg)

    @property
    def abierta(self) -> bool:
        return self.previos is None

    def bytes(self, etiqueta: bytes, datos: bytes) -> None:
        write_frame(self.s, etiqueta + datos)


def correr_vivo(snap, config: dict, entrada, salida_stream) -> None:
    ritmo = float(config.get("ritmo", 1.0))
    sal = _Salida(salida_stream)
    vivo = Vivo(snap, max_s=float(config.get("max_s") or 1800.0))
    cola: queue.Queue = queue.Queue()
    threading.Thread(target=_lector, args=(entrada, cola), daemon=True).start()
    paso_v = VENTANA_S * (ritmo if ritmo > 0 else 1.0)    # tiempo virtual por ventana
    historia: collections.deque = collections.deque(maxlen=VENTANAS_FACTOR)
    w_ref, v_ref, j = time.perf_counter(), 0.0, 0
    pausado, lento, motivo = False, False, None
    while motivo is None:
        # 1. lo que llegó
        while True:
            try:
                msg = cola.get_nowait()
            except queue.Empty:
                break
            if msg.get("_invalido"):
                sal.json({"tipo": "rechazo", "id": None, "motivo": "el mensaje no es JSON"})
                continue
            control = msg.get("control") if isinstance(msg, dict) else None
            if control in ("pausa", "reanudar", "parar"):
                try:
                    leer_mensaje(msg)
                except ValueError as exc:
                    sal.json({"tipo": "rechazo", "id": msg.get("id"), "motivo": str(exc)})
                    continue
                if control == "parar":
                    motivo = "cerrada" if msg.get("_eof") else "parada"
                    break
                if control == "pausa" and not pausado:
                    pausado = True
                    sal.json({"tipo": "pausa", "id": msg.get("id"), "t": round(vivo.t, 6)})
                elif control == "reanudar" and pausado:
                    pausado = False
                    w_ref, v_ref, j = time.perf_counter(), vivo.t, 0
                    historia.clear()
                    sal.json({"tipo": "reanudar", "id": msg.get("id"), "t": round(vivo.t, 6)})
                continue
            rechazo = vivo.recibir(msg)
            if rechazo is not None:
                sal.json(rechazo)
        if motivo is not None:
            break
        if pausado:
            time.sleep(TAJADA_S)
            continue
        # 2. avanzar hasta el objetivo de la ventana
        j += 1
        objetivo = v_ref + j * paso_v
        vivo.avanzar(max(0, int(round(objetivo / vivo.dt)) - vivo.k))
        # 3. publicar (la tabla, siempre lo primero)
        nuevas, valores = vivo.fot.reunir()
        if not sal.abierta:
            sal.abrir({"tipo": "tabla", **vivo.fot.tabla()})
            nuevas = []
        for r in vivo.respuestas():
            sal.json(r)
        ahora = time.perf_counter()
        historia.append((ahora, vivo.t))
        factor = ((historia[-1][1] - historia[0][1]) / (historia[-1][0] - historia[0][0])
                  if len(historia) > 1 and historia[-1][0] > historia[0][0] else (ritmo or 1.0))
        if nuevas:
            n0 = len(vivo.fot.senales) - len(nuevas)
            sal.json({"tipo": "senales", "desde": n0, "nombres": nuevas})
        textos = vivo.fot.textos_cambiados()
        if textos:
            sal.json({"tipo": "textos", "t": round(vivo.t, 6), "valores": textos})
        sal.bytes(b"F", vivo.fot.empacar(vivo.t, factor, valores))
        vivo.podar()
        if ritmo > 0 and len(historia) == VENTANAS_FACTOR:
            es_lento = factor < UMBRAL_LENTO * ritmo
            if es_lento != lento:
                lento = es_lento
                sal.json({"tipo": "factor", "factor": round(factor, 3), "lento": lento,
                          "mensaje": (f"la simulación va a ×{factor:.2f} del tiempo real: esta máquina "
                                      "no alcanza a la pared y sigue más lenta" if lento
                                      else "la simulación volvió al tiempo real")})
        if vivo.agotada:
            motivo = "tope"
            break
        # 4. dormir lo que sobre (reloj absoluto; una deuda grande se perdona)
        if ritmo <= 0:
            continue
        limite = w_ref + j * VENTANA_S
        if time.perf_counter() - limite > REBASE_S:
            w_ref, v_ref, j = time.perf_counter(), vivo.t, 0
            continue
        while True:
            falta = limite - time.perf_counter()
            if falta <= 0:
                break
            time.sleep(min(TAJADA_S, falta))
    if not sal.abierta:  # paró antes de la primera ventana (la tabla, sin señales)
        sal.abrir({"tipo": "tabla", **vivo.fot.tabla()})
    for r in vivo.respuestas():
        sal.json(r)
    sal.json({"tipo": "fin", "motivo": motivo, "t": round(vivo.t, 6), "intercambios": vivo.k,
              "grabacion": vivo.grabacion,
              **({"mensaje": f"la sesión llegó a su tope de {vivo.max_s:g} s virtuales"}
                 if motivo == "tope" else {})})
