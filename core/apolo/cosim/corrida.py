"""Una corrida de la co-simulación armada, y SU intercambio: lo que comparten el lote y el vivo.

`planificador.correr` (el lote, V8.3 D9) y `vivo.Vivo` (la sesión en vivo, V8.4 D1) avanzan el
MISMO estado con el MISMO paso, así una sesión viva grabada y vuelta escenario da las mismas
trazas por construcción:

    c = Corrida(snap)
    c.intercambio(k, trazas)               # agenda → MuJoCo → tablero → PLC → (trazas) → física
    c.intercambio(n, trazas, ultimo=True)  # el lote cierra sin física (la muestra forzada)

El orden dentro del intercambio es el de V8.3 (D8): la agenda del escenario en t = k·Δt, la
lectura de MuJoCo (ω, par, fotoceldas), el tablero (redes y modelos), cada PLC con t_ms = k·Δt en
ms ENTEROS, las trazas si las hay y, al final, los comandos de los motores hacia MuJoCo y
`Integrador.intercambio`. El costo de cada parte se mide con el reloj de pared, que no entra a
la huella.
"""

from __future__ import annotations

import time

from apolo.physics.dinamica_integrador import Integrador
from apolo.plc import PLC, RUN, SIN_TENSION

from .acople import AcopleMecanico
from .agenda import Agenda
from .externo import conectar
from .puerto_plc import LazoCortado, cerrar
from .tablero import Tablero


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
    if es.detenido or es.reanudar:  # la falla `detenido` de su hardware (cosim-fallas D2)
        if es.detenido:
            if plc.estado == RUN:
                plc.stop()
            tab.plc_salidas[des] = dict(plc.salidas)
            return
        es.reanudar = False
        if run:
            plc.run(t_ms)
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
    """`<pieza>.v_m_s` de cada banda y `<producto>.x_mm`, `.y_mm` y `.z_mm` de cada producto en la
    máquina (D10; `y_mm`/`z_mm` desde V8.9 F7b, defecto 5: un desvío lateral se afirma por la y).
    Uno RETIRADO por un sumidero se queda con la posición en que se retiró, la misma
    `posicion_final_mm` de la salida de la dinámica (balance-de-producto, bitácora de las trabas
    de flujo): «caja_3.x_mm >= 3500 al_final» dice si llegó, no «la señal no tiene valor»."""
    out: dict = {}
    if integ.arrastre is not None:
        for k, b in enumerate(integ.snap.bandas):
            out[f"{b.pieza}.v_m_s"] = signos[k] * integ.arrastre.v_banda(k)
    d, retiro = integ.d, integ.retiro
    for k, p in enumerate(integ.snap.productos):
        if integ.activo[k]:
            pos = [float(c) * 1000.0 for c in d.xpos[integ.bid_prod[k]]]
        elif k in retiro:
            pos = retiro[k]["pos"]
        else:
            continue
        nombre = p["name"][2:] if p["name"].startswith("p_") else p["name"]
        for eje, c in (("x", 0), ("y", 1), ("z", 2)):
            out[f"{nombre}.{eje}_mm"] = float(pos[c])
    return out


class Corrida:
    """El estado de una co-simulación (MuJoCo, tablero, PLC, acoples y agenda) sobre un
    `CosimSnapshot`, avanzado de a un intercambio."""

    def __init__(self, snap):
        self.snap = snap
        self.esc = esc = snap.escenario
        self.integ = Integrador(snap.dinamica)
        self.tab = Tablero(snap.red, snap.dispositivos, getattr(snap, "aire", None) or None)
        self.aire = self.tab.aire
        self.plcs: dict = {}
        externos = getattr(snap, "externos", None) or {}  # plc-en-el-lazo D6: los elige el pedido
        self.externos: dict = {}
        for p in snap.programas:
            if p.plc in externos:  # D4: la misma cara, de afuera (conectado y sin tensión)
                plc = self.externos[p.plc] = conectar(p, *externos[p.plc],
                                                      abiertos=list(self.externos.values()))
                self.plcs[p.plc] = plc
                continue
            plc = PLC(p.compilado, ciclo_ms=p.ciclo_ms, ciclos=p.ciclos or None)
            plc.cortar()  # sin tensión hasta que su fuente levante (lo decide su hardware)
            self.plcs[p.plc] = plc
        self.acople = AcopleMecanico(self.integ, snap.motores, snap.sensores,
                                     getattr(snap, "cilindros", ()), getattr(snap, "reeds", ()))
        self.agenda = Agenda(esc, self.tab, self.acople, plcs=self.plcs)  # `escribir` (plc-en-el-lazo D10)
        self.dt = self.integ.dt_int
        self.paso_ms = _paso_ms(self.dt)
        self.extra = set(esc.senales_extra)
        self.signos = _signos_banda(snap)
        self.costo = {"tablero": 0.0, "plc": 0.0, "fisica": 0.0, "trazas": 0.0}
        if self.aire is not None:  # V8.9 D4: la red de aire, con su costo aparte
            self.costo["aire"] = 0.0
        self._xv: dict = {}
        #: (k, índice del PLC) del intercambio que un PLC de afuera cortó a mitad (D8)
        self._reanudar: tuple[int, int] | None = None

    def cerrar(self) -> None:
        """Cierra los conectores de los PLC externos (sin ellos, nada)."""
        for plc in self.externos.values():
            cerrar(plc)

    def fuentes(self) -> list:
        """Las salidas de cada modelo y de cada PLC: [(prefijo, {nombre corto: valor})]."""
        return self.tab.salidas_por_prefijo() + _fuentes_plc(self.plcs)

    def analogicas_extra(self) -> dict:
        """Redes y mecánica (las caras: se piden sólo al muestrear)."""
        return {**self.tab.senales_red(self.extra), **_mecanica(self.integ, self.signos)}

    def intercambio(self, k: int, trazas=None, *, ultimo: bool = False) -> None:
        """El intercambio k (t = k·Δt). Con `ultimo` no avanza la física (el cierre del lote).

        Si un PLC de afuera corta el lazo en su etapa (plc-en-el-lazo D8), la corrida recuerda
        dónde: volver a llamar con el MISMO k sigue desde ese PLC, sin re-aplicar la agenda ni
        volver a integrar el tablero (la sesión viva pausada que reanuda)."""
        t = k * self.dt
        tab = self.tab
        sigue, self._reanudar = self._reanudar, None
        if sigue is not None and sigue[0] == k:
            desde = sigue[1]
            a = time.perf_counter()
        else:
            desde = 0
            self.agenda.aplicar(t)
            a = time.perf_counter()
            tab.mec, tab.detecta = self.acople.leer()
            if self.aire is not None:  # la posición del vástago al empezar el intercambio (D7)
                self._xv = self.acople.lecturas()
                for des, (x, v) in self._xv.items():
                    cil = tab.modelos[des]
                    cil.x, cil.v = x, v
            tab.paso(self.dt)
        b = time.perf_counter()
        for i, (des, plc) in enumerate(self.plcs.items()):
            if i < desde:
                continue
            try:
                _plc(des, plc, tab, k * self.paso_ms, self.esc.plc_run)
            except LazoCortado:  # sin externo nunca pasa: el PLC virtual no lo lanza
                self._reanudar = (k, i)
                raise
        c = time.perf_counter()
        if trazas is not None:
            trazas.registrar(k, t, self.fuentes(), self.analogicas_extra, forzar=ultimo)
        e = time.perf_counter()
        costo = self.costo
        costo["tablero"] += b - a
        costo["plc"] += c - b
        costo["trazas"] += e - c
        if ultimo:
            return
        fuerzas = frenos = None
        if self.aire is not None:  # V8.9 D4: las cámaras en sub-pasos, la fuerza media a MuJoCo
            fuerzas = self.aire.paso(self.dt, self._xv)
            frenos = self.aire.frenos  # plan bloqueo-de-vastago D4: {} sin bloqueos
            f = time.perf_counter()
            costo["aire"] += f - e
            e = f
        self.integ.intercambio(control=self.acople.control(tab.comandos, fuerzas, frenos))
        costo["fisica"] += time.perf_counter() - e
