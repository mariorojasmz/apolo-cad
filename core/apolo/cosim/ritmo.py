"""El ritmo de pared del lazo con un PLC de afuera (plan plc-en-el-lazo, D9).

El PLC virtual vive en el reloj virtual (k·Δt) y la corrida va tan rápido como puede. Un PLC de
verdad vive en el reloj de PARED: el intercambio k tiene que ocurrir en t₀ + k·Δt de pared, ni
antes (el PLC no alcanzaría a ver la entrada) ni mucho después. `RitmoPared` lo sostiene:

    ritmo = RitmoPared(dt)
    for k in range(n + 1):
        ritmo.esperar(k)          # duerme hasta t₀ + k·Δt
        corrida.intercambio(k)

  - duerme en tajadas mientras falte más de `ACTIVA_S` (1,5 ms: el sueño del sistema no es más
    fino que eso) y el resto lo espera en activo;
  - un intercambio que llega tarde es un ATRASADO (cuenta y guarda el atraso máximo); los que
    siguen corren sin esperar hasta ponerse al día;
  - una deuda de más de `REBASE_S` se PERDONA (t₀ se corre): ponerse al día a ráfagas le
    mostraría al PLC un tiempo comprimido.

Sólo con un PLC externo: sin él, la corrida de siempre, sin espera activa. Reloj y dormir
inyectables (los tests usan uno falso). Puro: stdlib.
"""

from __future__ import annotations

import time

#: Por debajo de esto se espera en activo.
ACTIVA_S = 0.0015
#: La tajada máxima de un sueño.
TAJADA_S = 0.010
#: Una deuda mayor que esto se perdona (criterio: 50 intercambios de 2 ms).
REBASE_S = 0.100


class RitmoPared:
    def __init__(self, dt: float, reloj=time.perf_counter, dormir=time.sleep, *,
                 rebase_s: float = REBASE_S):
        if not dt > 0:
            raise ValueError(f"el intercambio tiene que durar más de 0 s, no {dt!r}")
        self.dt = float(dt)
        self.reloj = reloj
        self.dormir = dormir
        self.rebase_s = float(rebase_s)
        self.t0: float | None = None
        self.intercambios = 0
        self.atrasados = 0
        self.atraso_max_s = 0.0
        self.rebases = 0

    def esperar(self, k: int) -> float:
        """Espera hasta t₀ + k·Δt (el primero fija t₀). Devuelve el atraso en s (0 si llegó a
        tiempo)."""
        ahora = self.reloj()
        self.intercambios += 1
        if self.t0 is None:
            self.t0 = ahora - k * self.dt
            return 0.0
        objetivo = self.t0 + k * self.dt
        falta = objetivo - ahora
        if falta < 0:
            atraso = -falta
            self.atrasados += 1
            self.atraso_max_s = max(self.atraso_max_s, atraso)
            if atraso > self.rebase_s:
                self.t0 = ahora - k * self.dt
                self.rebases += 1
            return atraso
        while falta > ACTIVA_S:
            self.dormir(min(falta - ACTIVA_S, TAJADA_S))
            falta = objetivo - self.reloj()
        while self.reloj() < objetivo:
            pass
        return 0.0

    def resumen(self) -> dict:
        return {"intercambios": self.intercambios, "atrasados": self.atrasados,
                "atraso_max_ms": round(self.atraso_max_s * 1000.0, 3), "rebases": self.rebases}
