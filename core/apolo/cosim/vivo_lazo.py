"""La sesión EN VIVO con un PLC de afuera (plan plc-en-el-lazo, D8 y D9 en vivo).

Sin PLC externo nada de esto corre: `worker_vivo` avanza a ráfagas de 1/30 s y duerme lo que
sobra, como siempre. Con uno (los `externos` de la `Corrida`, que eligió el pedido, D6):

  - D9: UN intercambio por vez a ritmo de pared (`RitmoPared`: el intercambio k en t₀ + k·Δt) y
    el fotograma cada 1/30 s VIRTUAL; el sueño de la ventana lo pone el ritmo, no el worker;
  - D8: un `LazoCortado` de cualquier miembro PAUSA la sesión (`{"tipo": "pausa", "motivo":
    "lazo", "mensaje"}`) y la máquina virtual no avanza más con las salidas viejas. Al
    reanudar, el intercambio cortado SIGUE desde el PLC que cortó (`Corrida.intercambio` lo
    recuerda): ni la agenda ni el tablero se vuelven a correr, así ningún Δt se integra dos
    veces. `reanudar` llama a `reconectar()` del conector si lo tiene; si corta otra vez,
    vuelve a la pausa con el motivo nuevo;
  - la pausa manual llama a `pausar()`/`reanudar()` del conector si los tiene, y el `fin` dice
    que el PLC de afuera siguió con su reloj durante la pausa (una máquina virtual se detiene;
    un PLC de verdad, no);
  - el `fin` suma `determinista: false` y el `lazo` medido por el NÚCLEO (D7: el ritmo y la ida
    y vuelta de `paso()`, de los últimos `IDAS_MAX` intercambios: una sesión dura hasta 30 min).
Puro: stdlib (corre en el worker).
"""

from __future__ import annotations

import collections

from .externo import lazo
from .puerto_plc import LazoCortado
from .ritmo import RitmoPared

#: La ida y vuelta se guarda de los últimos 60 s de intercambios de 2 ms (una sesión dura hasta
#: 30 min: la lista entera serían ~30 MB).
IDAS_MAX = 30_000


def _como_lazo(exc: Exception) -> LazoCortado:
    """Lo que lanza el código del conector, como `LazoCortado` (el motivo dice qué fue)."""
    return exc if isinstance(exc, LazoCortado) else LazoCortado(f"{type(exc).__name__}: {exc}")


class LazoVivo:
    """El ritmo, la pausa y el corte del lazo de una `Vivo` con PLC de afuera."""

    def __init__(self, vivo):
        self.vivo = vivo
        self.externos = vivo.c.externos
        for p in self.externos.values():  # `externo.Medido`: sólo la ventana reciente
            p.idas = collections.deque(p.idas, maxlen=IDAS_MAX)
        self.ritmo = RitmoPared(vivo.dt)
        self.hubo_pausa = False

    def avanzar(self, n: int) -> None:
        """n intercambios, cada uno a su hora de pared. `LazoCortado` con la hora virtual del
        intercambio que no pudo terminar (`vivo.k` sigue en él)."""
        v = self.vivo
        for _ in range(n):
            if v.agotada:
                return
            self.ritmo.esperar(v.k)
            try:
                v.avanzar(1)
            except LazoCortado as exc:
                if exc.t_s is None:
                    exc.t_s = round(v.t, 6)
                raise

    def _llamar(self, nombre: str) -> None:
        """`nombre()` de cada conector que lo tenga; lo que lance es `LazoCortado`."""
        for p in self.externos.values():
            fn = getattr(p, nombre, None)
            if callable(fn):
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001 — el código del conector también puede lanzar
                    raise _como_lazo(exc) from exc

    def pausar(self) -> None:
        """La pausa manual: avisa al conector (`pausar()`), si sabe."""
        self.hubo_pausa = True
        self._llamar("pausar")

    def reanudar(self, *, tras_corte: bool) -> None:
        """Al reanudar: `reconectar()` tras un corte, `reanudar()` tras una pausa manual; el ritmo
        vuelve a contar desde ahora (la pausa no es un atraso)."""
        self.hubo_pausa = True
        self._llamar("reconectar" if tras_corte else "reanudar")
        self.ritmo.t0 = None

    def pausa(self, exc: LazoCortado, ident=None) -> dict:
        """El mensaje de la pausa por lazo cortado (`ident`: el del «reanudar» que no pudo)."""
        self.hubo_pausa = True
        return {"tipo": "pausa", "id": ident, "motivo": "lazo", "t": round(self.vivo.t, 6),
                "mensaje": (f"{exc}. La máquina virtual quedó en pausa (no sigue con las salidas viejas "
                            "del PLC): revisa el PLC o su red y reanuda.")}

    def fin(self) -> dict:
        """Lo que el `fin` suma con un PLC de afuera."""
        out = {"determinista": False, "lazo": lazo(self.vivo.c, self.ritmo)}
        if self.hubo_pausa:
            des = ", ".join(sorted(self.externos))
            out["aviso_externo"] = (f"el PLC externo {des} siguió corriendo con su propio reloj durante la "
                                    "pausa: la máquina virtual se detuvo y él no (sus temporizadores y su "
                                    "memoria avanzaron)")
        return out
