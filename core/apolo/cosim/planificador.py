"""El planificador multi-tasa de la co-simulación (plan V8.3 D9): reloj virtual, determinista.

Tres tasas sobre UN reloj entero de intercambios (k):
  - física: `timestep` de V8.2 (1 ms), `nstep` pasos por intercambio dentro del `Integrador`;
  - intercambio (2 ms): agenda del escenario → lectura de MuJoCo (ω, par, fotoceldas) → tablero
    (redes + modelos, D8) → PLC → comandos de los motores hacia MuJoCo → física → trazas;
  - PLC: cada `ciclo_ms` de su tarea, con t_ms = k·Δt en ms ENTEROS (nunca el reloj de pared).
El mismo snapshot da trazas idénticas bit a bit (`trazas.huella`). El tiempo de pared sólo se
mide para el resumen y no entra en la huella.

El intercambio vive en `corrida.Corrida` (V8.4 F1): el lote (`correr`) y la sesión en vivo
(`vivo.Vivo`) usan el MISMO paso, así una sesión grabada da las mismas trazas por lote.

`correr(snap)` corre en el proceso que lo llame: en la API lo hace el worker (`worker.py`, D11).
Puro: de `apolo` importa `cosim`, `plc` y los módulos SIN OCCT de la física.
"""

from __future__ import annotations

import time

from .corrida import (  # noqa: F401 — los ayudantes del paso, re-exportados (scripts de medición)
    Corrida,
    _fuentes_plc,
    _mecanica,
    _paso_ms,
    _plc,
    _signos_banda,
)
from .trazas import Trazas, huella

AVISO = ("simulación a nivel sistema; no reemplaza la puesta en marcha real ni la firma de un "
         "electricista colegiado")


def correr(snap) -> dict:
    """Corre la co-simulación del `CosimSnapshot` y devuelve trazas, eventos y resumen."""
    t_ini = time.perf_counter()
    c = Corrida(snap)
    dt = c.dt
    trazas = Trazas(c.esc.analogicas_hz, dt)
    t_arm = time.perf_counter() - t_ini
    t0 = time.perf_counter()
    n = c.integ.n_int
    for k in range(n + 1):
        c.intercambio(k, trazas, ultimo=k == n)
    pared = time.perf_counter() - t0
    final = trazas.cerrar()
    salida_trazas = trazas.salida()
    eventos = c.agenda.eventos
    dur = n * dt
    return {
        "aviso": AVISO,
        "resumen": {
            "duracion_s": round(dur, 6), "intercambio_s": dt, "intercambios": n,
            "huella": huella(salida_trazas, eventos, final),
            "t_armado_s": round(t_arm, 4), "t_pared_s": round(pared, 4),
            "factor_tiempo_real": round(dur / pared, 3) if pared > 0 else None,
            "costo_us_por_intercambio": {k: round(v / max(n, 1) * 1e6, 2) for k, v in c.costo.items()}
            | {"total": round(pared / max(n, 1) * 1e6, 2)},
            "senales": {"discretas": len(salida_trazas["discretas"]),
                        "analogicas": len(salida_trazas["analogicas"]["senales"])},
            "resoluciones_potencia": c.tab.resoluciones_potencia,
        },
        "trazas": salida_trazas,
        "eventos": eventos,
        "final": final,
        "plc": {des: {"estado": plc.estado, "fallas": plc.fallas, "scans": plc.scans}
                for des, plc in c.plcs.items()},
        "mecanica": c.integ.salida(),
        "hipotesis": list(snap.hipotesis) + c.tab.hipotesis,
        "avisos": list(snap.avisos) + c.tab.avisos,
    }
