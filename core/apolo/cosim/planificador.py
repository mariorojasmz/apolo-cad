"""El planificador multi-tasa de la co-simulación (plan V8.3 D9): reloj virtual, determinista.

Tres tasas sobre UN reloj entero de intercambios (k):
  - física: `timestep` de V8.2 (1 ms), `nstep` pasos por intercambio dentro del `Integrador`;
  - intercambio (2 ms): agenda del escenario → lectura de MuJoCo (ω, par, fotoceldas) → tablero
    (redes + modelos, D8) → PLC → comandos de los motores hacia MuJoCo → física → trazas;
  - PLC: cada `ciclo_ms` de su tarea, con t_ms = k·Δt en ms ENTEROS (nunca el reloj de pared).
El mismo snapshot da trazas idénticas bit a bit (`trazas.huella`). El tiempo de pared sólo se
mide para el resumen y no entra en la huella.

`correr(snap)` corre en el proceso que lo llame: en la API lo hace el worker (`worker.py`, D11).
Puro: de `apolo` importa `cosim`, `plc` y los módulos SIN OCCT de la física.
"""

from __future__ import annotations

import time

from apolo.physics.dinamica_integrador import Integrador
from apolo.plc import PLC, SIN_TENSION

from .acople import AcopleMecanico
from .agenda import Agenda
from .tablero import Tablero
from .trazas import Trazas, huella

AVISO = ("simulación a nivel sistema; no reemplaza la puesta en marcha real ni la firma de un "
         "electricista colegiado")


def _paso_ms(dt: float) -> int:
    ms = round(dt * 1000.0)
    if ms < 1 or abs(ms - dt * 1000.0) > 1e-9:
        raise ValueError(f"el intercambio de {dt * 1000:g} ms no es un número entero de ms: el reloj "
                         "del PLC cuenta en ms (usa timestep × nstep = 1, 2, 4… ms)")
    return ms


def _plc(des: str, plc, tab: Tablero, t_ms: int, run: bool) -> None:
    """El PLC con su hardware: sin alimentación se apaga (y sus salidas caen); al volver,
    arranque en caliente; con alimentación, la imagen de entradas y su ciclo."""
    es = tab.modelos[des]
    if not es.alimentado:
        if plc.estado != SIN_TENSION:
            plc.cortar()
        tab.plc_salidas[des] = dict(plc.salidas)
        return
    if plc.estado == SIN_TENSION:
        plc.reponer(t_ms)
        if not run:
            plc.stop()
    for b in plc.compilado.entradas:
        plc.escribir_entrada(b, es.analog[b] if b.startswith("AI") else es.imagen[b])
    plc.paso(t_ms)
    tab.plc_salidas[des] = dict(plc.salidas)


def _fuentes_plc(plcs: dict) -> list:
    """[(«-A1.», {variable: valor, «estado», «falla»})] de cada PLC (D10: «-A1.Main.cuenta»)."""
    return [(f"{des}.", {**plc.variables(), "estado": plc.estado, "falla": (plc.falla or {}).get("tipo", "")})
            for des, plc in plcs.items()]


def _signos_banda(snap) -> list[float]:
    """+1/−1 por banda: `<pieza>.v_m_s` es positiva HACIA la dirección de transporte (la de la
    banda, o la del motor acoplado a su junta), no con el giro positivo del eje."""
    out = []
    for b in snap.dinamica.bandas:
        s = b.signo if b.signo is not None else next((a.signo for a in snap.motores if a.junta == b.junta), 1.0)
        out.append(float(s))
    return out


def _mecanica(integ, signos: list) -> dict:
    """`<pieza>.v_m_s` de cada banda y `<producto>.x_mm` de cada producto en la máquina (D10)."""
    out: dict = {}
    if integ.arrastre is not None:
        for k, b in enumerate(integ.snap.bandas):
            out[f"{b.pieza}.v_m_s"] = signos[k] * integ.arrastre.v_banda(k)
    d = integ.d
    for k, p in enumerate(integ.snap.productos):
        if integ.activo[k]:
            nombre = p["name"][2:] if p["name"].startswith("p_") else p["name"]
            out[f"{nombre}.x_mm"] = float(d.xpos[integ.bid_prod[k]][0]) * 1000.0
    return out


def correr(snap) -> dict:
    """Corre la co-simulación del `CosimSnapshot` y devuelve trazas, eventos y resumen."""
    t_ini = time.perf_counter()
    esc = snap.escenario
    integ = Integrador(snap.dinamica)
    tab = Tablero(snap.red, snap.dispositivos)
    plcs = {}
    for p in snap.programas:
        plc = PLC(p.compilado, ciclo_ms=p.ciclo_ms, ciclos=p.ciclos or None)
        plc.cortar()  # sin tensión hasta que su fuente levante (lo decide su hardware)
        plcs[p.plc] = plc
    acople = AcopleMecanico(integ, snap.motores, snap.sensores)
    agenda = Agenda(esc, tab, acople)
    dt = integ.dt_int
    paso_ms = _paso_ms(dt)
    trazas = Trazas(esc.analogicas_hz, dt)
    extra = set(esc.senales_extra)
    signos = _signos_banda(snap)
    costo = {"tablero": 0.0, "plc": 0.0, "fisica": 0.0, "trazas": 0.0}
    t_arm = time.perf_counter() - t_ini
    t0 = time.perf_counter()
    n = integ.n_int
    for k in range(n + 1):
        t = k * dt
        agenda.aplicar(t)
        a = time.perf_counter()
        tab.mec, tab.detecta = acople.leer()
        tab.paso(dt)
        b = time.perf_counter()
        for des, plc in plcs.items():
            _plc(des, plc, tab, k * paso_ms, esc.plc_run)
        c = time.perf_counter()
        trazas.registrar(k, t, tab.salidas_por_prefijo() + _fuentes_plc(plcs),
                         lambda: {**tab.senales_red(extra), **_mecanica(integ, signos)}, forzar=k == n)
        e = time.perf_counter()
        costo["tablero"] += b - a
        costo["plc"] += c - b
        costo["trazas"] += e - c
        if k == n:
            break
        integ.intercambio(control=acople.control(tab.comandos))
        costo["fisica"] += time.perf_counter() - e
    pared = time.perf_counter() - t0
    final = trazas.cerrar()
    salida_trazas = trazas.salida()
    eventos = agenda.eventos
    dur = n * dt
    return {
        "aviso": AVISO,
        "resumen": {
            "duracion_s": round(dur, 6), "intercambio_s": dt, "intercambios": n,
            "huella": huella(salida_trazas, eventos, final),
            "t_armado_s": round(t_arm, 4), "t_pared_s": round(pared, 4),
            "factor_tiempo_real": round(dur / pared, 3) if pared > 0 else None,
            "costo_us_por_intercambio": {c: round(v / max(n, 1) * 1e6, 2) for c, v in costo.items()}
            | {"total": round(pared / max(n, 1) * 1e6, 2)},
            "senales": {"discretas": len(salida_trazas["discretas"]),
                        "analogicas": len(salida_trazas["analogicas"]["senales"])},
            "resoluciones_potencia": tab.resoluciones_potencia,
        },
        "trazas": salida_trazas,
        "eventos": eventos,
        "final": final,
        "plc": {des: {"estado": plc.estado, "fallas": plc.fallas, "scans": plc.scans}
                for des, plc in plcs.items()},
        "mecanica": integ.salida(),
        "hipotesis": list(snap.hipotesis) + tab.hipotesis,
        "avisos": list(snap.avisos) + tab.avisos,
    }
