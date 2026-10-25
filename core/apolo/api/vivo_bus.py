"""El bus de la sesión viva, EN PROCESO (plan plc-en-el-lazo D11): una extensión sigue la sesión
que abrió la persona y le manda acciones, sin abrir otra (V8.4 D10) ni un segundo WebSocket.

- `suscribir(nombre, max_fotogramas=60) -> Suscripcion`: desde ese momento la suscripción recibe
  LO MISMO que el WebSocket y en su orden (`inicio`, fotogramas, `senales`, `textos`, acks y
  rechazos, `pausa`/`reanudar`, `fin`…), de la sesión abierta y de las que se abran después,
  hasta `cerrar()`. Quien llega con una sesión ya abierta (pedidos-de-extensiones D11) recibe
  PRIMERO, en orden, el `inicio` de esa sesión con `tarde: true`, cada `senales` que salió y un
  `textos` (también con `tarde: true`) con el último valor de cada texto; después, lo que siga:
  los fotogramas se leen con esa tabla. Lo guardado se olvida con el `fin`, al abrir otra sesión
  y al `cerrar` la suya; sin sesión abierta no hay nada que repetir. `recibir(timeout)` da un dict (JSON) o `bytes` (un fotograma, formato de
  `cosim/vivo_fotograma.py`). Cada suscripción tiene su cola ACOTADA: pasados `max_fotogramas`
  sin leer se descarta el fotograma más VIEJO (`descartados`) y pasados `MAX_JSON` mensajes, el
  JSON nuevo (`json_descartados`), salvo `inicio`, `senales` y `fin`, sin los que los fotogramas
  no se leen ni se sabe que la sesión terminó. La cola de la persona no se toca.
- `enviar_vivo(nombre, msg) -> bool`: una acción o un evento (dict o texto JSON) a la sesión
  abierta. Pasa la validación del WebSocket (`validar_texto`: tamaño, JSON, objeto) y NUNCA lleva
  controles (pausar, reanudar y parar son de la persona). Su `id` viaja con el prefijo
  `<nombre>:` (sin `id`, uno correlativo) y su ack o rechazo vuelve SÓLO a la suscripción
  `nombre` (si no hay, a nadie): ni a la persona ni a otra suscripción. `False` si no hay sesión
  abierta o el mensaje no pasa (su rechazo, entonces, a la suscripción). La grabación no
  distingue de dónde vino la acción.

Coreografía: `SesionViva._poner` (router `cosim_vivo`, en el loop) llama `BUS.difundir_json` /
`BUS.difundir_fotograma` con cada mensaje ya en la forma del WebSocket (el JSON con la sesión que
lo emitió: su `inicio` puede llegar antes que `BUS.abrir`), y registra la sesión con
`BUS.abrir`/`BUS.cerrar`. Los locks de aquí son HOJA (el del bus y uno por suscripción): copiar a
una suscripción es un `append`, así que un suscriptor que no lee no frena a la persona. El único
anidado es el de `suscribir`, que llena bajo el lock del bus la cola de una suscripción NUEVA
(todavía de nadie: su lock no puede estar tomado), para que ningún mensaje se adelante a la
repetición. Nada aquí toma `STATE_LOCK` ni importa `apolo.state` (lo vigila `tests/test_vivo_bus.py`).
"""

from __future__ import annotations

import collections
import json
import re
import threading

MAX_MENSAJE = 4096                # el tope del WebSocket (`cosim_vivo.MAX_MENSAJE` es este)
MAX_JSON = 1000                   # mensajes JSON sin leer por suscripción
ESTRUCTURA = frozenset({"inicio", "senales", "fin"})   # nunca se descartan
_NOMBRE = re.compile(r"^[a-z][a-z0-9_]*\.[A-Za-z0-9_.-]{1,60}$")
CONTROL = ("los controles (pausa, reanudar, parar) son de la persona: una extensión manda acciones "
           "y eventos")


def validar_texto(texto: str) -> tuple[dict | None, str | None]:
    """La validación de un mensaje del cliente, la MISMA para el WebSocket y el bus: (msg, None)
    o (None, motivo del rechazo)."""
    if len(texto) > MAX_MENSAJE:
        return None, f"mensaje de más de {MAX_MENSAJE} bytes"
    try:
        msg = json.loads(texto)
    except ValueError:
        return None, "el mensaje no es JSON"
    if not isinstance(msg, dict):
        return None, "se espera un objeto: {\"pulsar\": \"-S1\"}"
    return msg, None


class Suscripcion:
    """Lo que ve una extensión de la sesión viva. Se crea con `suscribir`; `cerrar()` (o salir
    del `with`) libera el nombre."""

    def __init__(self, nombre: str, max_fotogramas: int, bus: Bus):
        self.nombre = nombre
        self.max_fotogramas = max_fotogramas
        self.descartados = 0          # fotogramas viejos descartados
        self.json_descartados = 0     # mensajes JSON descartados (nunca `inicio`, `senales`, `fin`)
        self.cerrada = False
        self._bus = bus
        self._cv = threading.Condition()   # HOJA
        self._cola: collections.deque = collections.deque()
        self._fotogramas = 0
        self._json = 0

    @property
    def pendientes(self) -> int:
        with self._cv:
            return len(self._cola)

    def _poner(self, item, tipo: str | None = None) -> None:
        """`item`: `bytes` (fotograma) o el texto JSON con su `tipo`."""
        with self._cv:
            if self.cerrada:
                return
            if isinstance(item, bytes):
                if self._fotogramas >= self.max_fotogramas:
                    self.descartados += 1
                    viejo = next((i for i, x in enumerate(self._cola) if isinstance(x, bytes)), None)
                    if viejo is None:   # max_fotogramas = 0: sólo JSON
                        return
                    del self._cola[viejo]
                    self._fotogramas -= 1
                self._fotogramas += 1
            elif self._json >= MAX_JSON and tipo not in ESTRUCTURA:
                self.json_descartados += 1
                return
            else:
                self._json += 1
            self._cola.append(item)
            self._cv.notify_all()

    def recibir(self, timeout: float | None = None):
        """El próximo mensaje: un dict (JSON, una copia propia) o `bytes` (un fotograma). None si
        no llegó nada en `timeout` s (None = esperar) o la suscripción está cerrada."""
        with self._cv:
            if not self._cv.wait_for(lambda: self._cola or self.cerrada, timeout) or not self._cola:
                return None
            x = self._cola.popleft()
            if isinstance(x, bytes):
                self._fotogramas -= 1
                return x
            self._json -= 1
        return json.loads(x)

    def cerrar(self) -> None:
        """Deja de recibir (lo pendiente se pierde) y libera el nombre. Idempotente."""
        self._bus._quitar(self)
        with self._cv:
            self.cerrada = True
            self._cola.clear()
            self._fotogramas = self._json = 0
            self._cv.notify_all()

    def __enter__(self) -> Suscripcion:
        return self

    def __exit__(self, *_exc) -> None:
        self.cerrar()


class Bus:
    """Las suscripciones y la sesión viva abierta. Un objeto por proceso (`BUS`)."""

    def __init__(self):
        self._lock = threading.Lock()      # HOJA
        self._subs: dict[str, Suscripcion] = {}
        self._sesion = None                # lo que registró `abrir`: `.enviar(msg) -> bool`
        self._en_vuelo: collections.Counter = collections.Counter()   # ids con prefijo sin respuesta
        self._n = 0
        self._memoria: _Memoria | None = None   # D11: la sesión abierta, para quien llega tarde

    # ── lo que usa una extensión ─────────────────────────────────────────────────────────────
    def suscribir(self, nombre: str, max_fotogramas: int = 60) -> Suscripcion:
        if not isinstance(nombre, str) or not _NOMBRE.match(nombre):
            raise ValueError(f"nombre de suscripción {nombre!r}: lleva el prefijo de la extensión "
                             "(«prefijo.algo», sin «:»)")
        if isinstance(max_fotogramas, bool) or not isinstance(max_fotogramas, int) or max_fotogramas < 0:
            raise ValueError(f"max_fotogramas {max_fotogramas!r}: un entero ≥ 0")
        with self._lock:
            if nombre in self._subs:
                raise ValueError(f"ya hay una suscripción «{nombre}»: ciérrala antes (sus acks irían "
                                 "a una sola)")
            sub = Suscripcion(nombre, max_fotogramas, self)
            if self._memoria is not None:   # D11: la sesión ya abierta, antes que nada
                for texto, tipo in self._memoria.repeticion():
                    sub._poner(texto, tipo)
            self._subs[nombre] = sub
        return sub

    def enviar(self, nombre: str, msg) -> bool:
        if not isinstance(nombre, str) or not _NOMBRE.match(nombre):
            raise ValueError(f"nombre {nombre!r}: el de la suscripción («prefijo.algo»)")
        if isinstance(msg, str):
            texto = msg
        else:
            try:
                texto = json.dumps(msg, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError):
                texto = ""   # → «el mensaje no es JSON»
        obj, motivo = validar_texto(texto)
        if obj is not None and "control" in obj:
            motivo = CONTROL
        with self._lock:
            sesion, sub = self._sesion, self._subs.get(nombre)
            if obj is not None:
                if obj.get("id") is None:
                    self._n += 1
                ident = f"{nombre}:{obj['id'] if obj.get('id') is not None else self._n}"
        if motivo is not None:
            if sub is not None:
                sub._poner(json.dumps({"tipo": "rechazo", "id": ident if obj is not None else None,
                                       "motivo": motivo}, ensure_ascii=False), "rechazo")
            return False
        if sesion is None:
            return False
        with self._lock:
            self._en_vuelo[ident] += 1   # antes de enviar: el ack puede volver enseguida
        if sesion.enviar({**obj, "id": ident}):
            return True
        with self._lock:
            self._olvidar(ident)
        return False

    # ── lo que usa la sesión viva (router `cosim_vivo`, en el loop) ─────────────────────────────
    def abrir(self, sesion) -> None:
        with self._lock:
            self._sesion = sesion
            self._en_vuelo.clear()   # lo que quedó sin respuesta de la sesión anterior
            if self._memoria is not None and self._memoria.sesion is not sesion:
                self._memoria = None   # la de otra sesión (la suya pudo llegar antes que `abrir`)

    def cerrar(self, sesion) -> None:
        with self._lock:
            if self._sesion is sesion:
                self._sesion = None
            if self._memoria is not None and self._memoria.sesion is sesion:
                self._memoria = None

    def difundir_json(self, msg: dict, texto: str, sesion=None) -> bool:
        """`texto` (el JSON que va al WebSocket) a cada suscripción. True si es la respuesta a una
        acción del bus: va SÓLO a su suscripción (o a nadie, si ya cerró) y no a la persona.
        `sesion`, la que lo emitió: su `inicio`, sus `senales` y sus `textos` quedan guardados
        para quien se suscriba tarde (D11), aunque ahora no haya ninguna suscripción."""
        with self._lock:
            self._recordar(msg, texto, sesion)
            if not self._subs and not self._en_vuelo:
                return False
            ident = msg.get("id")
            if (msg.get("tipo") in ("ack", "rechazo") and isinstance(ident, str)
                    and self._en_vuelo[ident] > 0):
                self._olvidar(ident)
                destinos, privado = [self._subs.get(ident.split(":", 1)[0])], True
            else:
                destinos, privado = list(self._subs.values()), False
        for sub in destinos:
            if sub is not None:
                sub._poner(texto, msg.get("tipo"))
        return privado

    def difundir_fotograma(self, cuerpo: bytes) -> None:
        with self._lock:
            destinos = list(self._subs.values())
        for sub in destinos:
            sub._poner(cuerpo)

    # ── interno ──────────────────────────────────────────────────────────────────────────────
    def _recordar(self, msg: dict, texto: str, sesion) -> None:
        """Bajo `_lock` (el que elige los destinos): lo de la sesión que verá quien llegue tarde."""
        tipo = msg.get("tipo")
        if tipo == "inicio":
            self._memoria = _Memoria(sesion, texto)
            return
        mem = self._memoria
        if mem is None or mem.sesion is not sesion:   # otra sesión (una reemplazada que se apaga)
            return
        if tipo == "fin":
            self._memoria = None
        elif tipo == "senales":
            mem.senales.append(texto)
        elif tipo == "textos" and isinstance(msg.get("valores"), dict):
            mem.textos.update(msg["valores"])
            mem.t = msg.get("t")

    def _olvidar(self, ident: str) -> None:
        self._en_vuelo[ident] -= 1
        if self._en_vuelo[ident] <= 0:
            del self._en_vuelo[ident]

    def _quitar(self, sub: Suscripcion) -> None:
        with self._lock:
            if self._subs.get(sub.nombre) is sub:
                del self._subs[sub.nombre]


class _Memoria:
    """Lo que recibe primero quien llega tarde a una sesión (D11): el texto de su `inicio`, cada
    `senales` en orden y el último valor de cada texto."""

    def __init__(self, sesion, inicio: str):
        self.sesion = sesion
        # el mismo JSON con `tarde: true` al final (el `inicio` es siempre un objeto no vacío)
        self.inicio = inicio.rstrip()[:-1] + ',"tarde":true}'
        self.senales: list[str] = []
        self.textos: dict = {}
        self.t = None

    def repeticion(self) -> list[tuple[str, str]]:
        """[(texto JSON, tipo)] en el orden en que los recibe la suscripción nueva."""
        out = [(self.inicio, "inicio"), *((s, "senales") for s in self.senales)]
        if self.textos:
            out.append((json.dumps({"tipo": "textos", "t": self.t, "valores": self.textos, "tarde": True},
                                   ensure_ascii=False, separators=(",", ":")), "textos"))
        return out


BUS = Bus()


def suscribir(nombre: str, max_fotogramas: int = 60) -> Suscripcion:
    """Sigue la sesión viva (la abierta y las que vengan) con el nombre `nombre` («prefijo.algo»,
    el prefijo de la extensión). `ValueError` si el nombre no va o ya está suscrito."""
    return BUS.suscribir(nombre, max_fotogramas)


def enviar_vivo(nombre: str, msg) -> bool:
    """Una acción o un evento a la sesión viva abierta; su ack vuelve a la suscripción `nombre`.
    `False` sin sesión abierta o si el mensaje no pasa (su rechazo, a la suscripción)."""
    return BUS.enviar(nombre, msg)
