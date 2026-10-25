"""El lote con un PLC de afuera (plan plc-en-el-lazo, D6–D9): conectar, el ritmo de pared, el
lazo cortado con su hora y lo que el NÚCLEO mide del lazo.

Sólo actúa si el snapshot trae `externos` (lo elige el pedido de la corrida, D6): sin él,
`Corrida` arma `apolo.plc.PLC` como siempre y el lote corre sin ritmo de pared.

  - `conectar`: construye el conector (eso conecta) y le corta la alimentación virtual, como al
    PLC virtual al nacer; si falla, cierra los ya abiertos y la corrida no arranca;
  - `Medido`: el conector con la ida y vuelta de su `paso()` medida por el núcleo (D7: un número
    que reporta el conector no sería verificable);
  - `correr_a_la_pared`: el bucle del lote con `RitmoPared` (D9); un `LazoCortado` sale con la
    hora virtual del intercambio (D8) y los conectores se cierran siempre;
  - `anotar`: lo que el resultado suma (D7): `resumen.determinista = false` y `lazo`.
Puro: stdlib.
"""

from __future__ import annotations

import time

from .puerto_plc import LazoCortado, cerrar
from .ritmo import RitmoPared


class Medido:
    """El conector, con la ida y vuelta de cada `paso()` en `idas` (s). El resto, tal cual."""

    def __init__(self, puerto, reloj=time.perf_counter):
        self.puerto = puerto
        self.idas: list[float] = []
        self._reloj = reloj

    def paso(self, t_ms: int):
        a = self._reloj()
        try:
            return self.puerto.paso(t_ms)
        finally:
            self.idas.append(self._reloj() - a)

    def __getattr__(self, nombre: str):
        return getattr(self.puerto, nombre)


def conectar(programa, clase, config: dict, abiertos=()) -> Medido:
    """El conector de `programa.plc`, conectado y sin tensión virtual. `LazoCortado` si no pudo
    (y cierra `abiertos`: los de las otras designaciones)."""
    puerto = None
    try:
        puerto = clase(programa, dict(config))
        puerto.cortar()  # sin tensión hasta que su fuente levante (como el PLC virtual)
    except Exception as exc:  # noqa: BLE001 — el código del conector también puede lanzar
        for p in [*abiertos, puerto]:
            if p is not None:
                cerrar(p)
        motivo = exc.motivo if isinstance(exc, LazoCortado) else f"{type(exc).__name__}: {exc}"
        raise LazoCortado(f"no se pudo conectar el PLC externo {programa.plc}: {motivo}") from exc
    return Medido(puerto)


def correr_a_la_pared(c, trazas, n: int, ritmo: RitmoPared | None = None) -> RitmoPared:
    """Los intercambios 0…n de la corrida `c` a ritmo de pared. Cierra los conectores al salir."""
    ritmo = ritmo or RitmoPared(c.dt)
    try:
        for k in range(n + 1):
            ritmo.esperar(k)
            try:
                c.intercambio(k, trazas, ultimo=k == n)
            except LazoCortado as exc:
                if exc.t_s is None:
                    exc.t_s = round(k * c.dt, 6)
                raise
    finally:
        c.cerrar()
    return ritmo


def _estadistica(idas: list[float]) -> dict:
    """mediana, p99 (rango más cercano) y máximo en ms, y cuántos."""
    if not idas:
        return {"n": 0, "mediana_ms": None, "p99_ms": None, "max_ms": None}
    xs = sorted(idas)
    n = len(xs)
    mediana = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
    p99 = xs[min(n - 1, max(0, -(-99 * n // 100) - 1))]
    return {"n": n, "mediana_ms": round(mediana * 1000, 3), "p99_ms": round(p99 * 1000, 3),
            "max_ms": round(xs[-1] * 1000, 3)}


def lazo(c, ritmo: RitmoPared) -> dict:
    """El lazo medido por el núcleo: el ritmo (intercambios, atrasados, atraso máximo, rebases) y
    la ida y vuelta de `paso()` de cada PLC externo."""
    return {**ritmo.resumen(),
            "ida_y_vuelta": {des: _estadistica(p.idas) for des, p in c.externos.items()}}


AVISO = ("con un PLC externo la corrida NO es determinista (su reloj es el de pared y su programa "
         "no es el del documento): sirve para comparar, no como prueba")


def anotar(res: dict, c, ritmo: RitmoPared) -> dict:
    """D7: el resultado dice que no es determinista y trae el lazo medido."""
    res["resumen"]["determinista"] = False
    res["lazo"] = lazo(c, ritmo)
    res["avisos"] = [AVISO, *res.get("avisos", [])]
    return res
