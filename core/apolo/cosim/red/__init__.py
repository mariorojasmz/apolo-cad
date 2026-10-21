"""Las dos redes de la co-simulación (plan V8.3 F3; marco V8 D3 y D15).

  - **mando** (`RedMando`): continua de 24 V (y los 10 V del potenciómetro), MNA real con la LU
    en caché, refactorizada SÓLO cuando conmuta un contacto o cambia una impedancia;
  - **potencia** (`RedPotencia`): alterna fasorial cuasi-estática por fase (1F+N, 2F, 3F, 3F+N),
    con la alterna de MANDO adentro (la bobina de 220 VAC está unida a la red).

`armar(entrada)` lee el formato plano (`entrada.py`) y reparte por dominio (`topologia.py`).
En cada paso cada red recibe los estados de los contactos y fuentes que dan los modelos de F2
(`cosim/modelos`) y devuelve las tensiones y corrientes que esos modelos consumen. Puro: numpy y
el LAPACK de scipy, sin MuJoCo, OCCT ni `apolo.library` (`tests/test_capas_cosim.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .entrada import CargaRed, EntradaInvalida, EntradaRed, FuenteRed, Rama, leer_entrada
from .fasores import desbalance_pct, fasores_nominales
from .mando import RedMando, ResultadoMando
from .potencia import RedPotencia, ResultadoPotencia
from .topologia import Topologia


@dataclass
class Redes:
    mando: RedMando | None
    potencia: RedPotencia | None
    avisos: list[str] = field(default_factory=list)
    hipotesis: list[str] = field(default_factory=list)


def armar(entrada, *, temperatura_C: float | None = None) -> Redes:
    """Las dos redes de un formato plano (dict o `EntradaRed`). Una red sin fuentes es None."""
    e = leer_entrada(entrada)
    avisos = list(e.avisos)
    hipotesis = list(e.hipotesis)
    T = temperatura_C if temperatura_C is not None else e.temperatura_C
    topo = Topologia(e)
    kw = dict(temperatura_C=T, avisos=avisos, hipotesis=hipotesis, actuadores=e.actuadores)
    dm = topo.dominio("mando", avisos)
    dp = topo.dominio("potencia", avisos)
    return Redes(RedMando(dm, **kw) if dm else None, RedPotencia(dp, **kw) if dp else None,
                 avisos, hipotesis)


__all__ = ["CargaRed", "EntradaInvalida", "EntradaRed", "FuenteRed", "Rama", "RedMando", "RedPotencia",
           "Redes", "ResultadoMando", "ResultadoPotencia", "armar", "desbalance_pct",
           "fasores_nominales", "leer_entrada"]
