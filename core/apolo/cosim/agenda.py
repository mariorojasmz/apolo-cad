"""La agenda del escenario: condiciones iniciales, acciones del operador y eventos del mundo
(plan V8.3 D12), aplicados con el reloj virtual.

Cada acción o evento se aplica en el PRIMER intercambio con t ≥ su hora; uno con `duracion_s`
agenda su reverso. Lo aplicado queda en `eventos` con la hora real y la programada: son las
anclas de las aserciones «dentro_de Δ desde <acción o evento>» (F5).

`validar` corre la agenda entera sobre un tablero DESECHABLE antes de simular: un dispositivo
que no existe, una acción que no admite o una rama que no se puede cortar es error accionable en
el snapshot, no a mitad de la co-simulación.

`escribir` (plan plc-en-el-lazo D10) va a la memoria del programa de un PLC de la corrida
(`plcs`, los de `Corrida` o, en `validar`, los de `plcs_de_prueba`): la ruta y el tipo del valor
se validan contra su `Compilado` (también con un PLC de afuera, antes de pasársela a su
conector, que la recibe sólo si trae `escribir`). Un PLC SIN TENSIÓN no la atiende: en el lote
queda en `eventos` como `{"rechazo": "escribir", …, "motivo"}` (sin `accion`: no es ancla) y la
corrida sigue; en vivo es el rechazo de esa acción.
"""

from __future__ import annotations

import difflib

from apolo.plc import PLC, SIN_TENSION
from apolo.plc.simbolos import escritura

from . import fallas
from .escenario import Accion, EscenarioInvalido, Evento
from .neumatica.orificio import P_ATM_PA
from .puerto_plc import LazoCortado

EPS_T = 1e-9


class Agenda:
    def __init__(self, esc, tablero, acople=None, *, juntas: set | None = None, plcs: dict | None = None):
        self.esc, self.tab, self.acople = esc, tablero, acople
        self.juntas = juntas
        self.plcs = plcs or {}
        items: list = []
        for a in esc.acciones:
            items.append((a.t, len(items), a, False))
        for e in esc.eventos:
            items.append((e.t, len(items), e, False))
            if e.duracion_s:
                items.append((e.t + e.duracion_s, len(items), e, True))
        self.items = sorted(items, key=lambda x: (x[0], x[1]))
        self.i = 0
        self.eventos: list[dict] = []
        self._seq = len(items)
        #: seq de lo inyectado en vivo → su id (V8.4 D1): su error vuelve en `respuestas`
        self._inyectadas: dict[int, object] = {}
        self.respuestas: list[dict] = []
        self._iniciales()

    def inyectar(self, x, t: float, ident=None) -> None:
        """Agenda una acción o un evento SIN hora (la sesión en vivo, V8.4 D1) para el instante t,
        ORDENADO por (t, seq) desde la posición actual: va después de lo ya agendado a la misma
        hora, como en un escenario por lote. Un evento con `duracion_s` agenda su reverso. Al
        aplicarse deja en `respuestas` {id, ok, t} o {id, ok: false, motivo}: un error del modelo
        (dispositivo, acción o valor que no van) rechaza ESA acción y la corrida sigue."""
        nuevos = [(t, x, False)]
        if isinstance(x, Evento) and x.duracion_s:
            nuevos.append((t + x.duracion_s, x, True))
        for tt, xx, reverso in nuevos:
            item = (tt, self._seq, xx, reverso)
            if not reverso:
                self._inyectadas[self._seq] = ident
            self._seq += 1
            j = self.i
            while j < len(self.items) and (self.items[j][0], self.items[j][1]) <= (tt, item[1]):
                j += 1
            self.items.insert(j, item)

    def _modelo(self, des: str):
        m = self.tab.modelos.get(des)
        if m is None:
            parecida = difflib.get_close_matches(des, sorted(self.tab.modelos), n=1)
            pista = f" ¿Quisiste decir «{parecida[0]}»?" if parecida else ""
            raise ValueError(f"el tablero no tiene el dispositivo «{des}» (o es pasivo).{pista}")
        return m

    def _iniciales(self) -> None:
        esc = self.esc
        if not esc.red_conectada:
            for _des, red, _fid in self.tab.redes_ac:
                red.accionar("cortar")
        for des, pos in esc.selectores.items():
            self._modelo(des).accionar("girar", pos)
        for des in esc.setas_retenidas:
            self._modelo(des).accionar("presionar")

    def aplicar(self, t: float) -> None:
        while self.i < len(self.items) and self.items[self.i][0] <= t + EPS_T:
            t_prog, seq, x, reverso = self.items[self.i]
            self.i += 1
            if seq in self._inyectadas:
                self._aplicar_inyectada(t, t_prog, seq, x)
                continue
            if isinstance(x, Accion):
                motivo = self._accion(x)
                reg = _registro(x)
                if motivo:  # escribir a un PLC sin tensión: rechazo grabado, la corrida sigue
                    reg = {"rechazo": reg.pop("accion"), **reg, "motivo": motivo}
            else:
                self._evento(x, reverso)
                reg = {"evento": x.tipo + (".fin" if reverso else ""), **x.datos}
            self.eventos.append({"t": round(t, 6), "programado_s": round(t_prog, 6), **reg})

    def _aplicar_inyectada(self, t: float, t_prog: float, seq: int, x) -> None:
        ident = self._inyectadas.pop(seq)
        try:
            if isinstance(x, Accion):
                motivo = self._accion(x)
                if motivo:
                    raise ValueError(motivo)
                reg = _registro(x)
            else:
                self._evento(x, False)
                reg = {"evento": x.tipo, **x.datos}
        except (ValueError, KeyError) as exc:
            if isinstance(x, Evento) and x.duracion_s:  # sin el evento, su reverso tampoco
                self.items = [it for it in self.items if not (it[2] is x and it[3])]
            self.respuestas.append({"id": ident, "ok": False, "motivo": str(exc).strip("'\"")})
            return
        except LazoCortado as exc:  # plc-en-el-lazo D8: la acción no se pierde sin respuesta
            self.respuestas.append({"id": ident, "ok": False,
                                    "motivo": f"el lazo con el PLC externo se cortó al aplicarla: {exc.motivo}"})
            raise
        self.eventos.append({"t": round(t, 6), "programado_s": round(t_prog, 6), **reg})
        self.respuestas.append({"id": ident, "ok": True, "t": round(t, 6)})

    # ── acciones del operador ───────────────────────────────────────────────────────────────

    def _accion(self, a: Accion) -> str | None:
        """Aplica la acción; el motivo si un PLC sin tensión no atiende un `escribir`."""
        if a.accion == "escribir":
            return self._escribir(a)
        m = self._modelo(a.dispositivo)
        valor = a.valor
        if a.accion in ("pulsar", "soltar") and (a.actuador or a.durante_s is not None):
            valor = {"actuador": a.actuador, "durante_s": a.durante_s}
        if a.accion not in m.ACCIONES:
            raise ValueError(f"{a.dispositivo} ({m.ref}, {m.tipo}) no admite «{a.accion}»; "
                             f"acciones: {', '.join(m.ACCIONES) or '(ninguna)'}")
        m.accionar(a.accion, valor)
        return None

    def _escribir(self, a: Accion) -> str | None:
        plc = self.plcs.get(a.dispositivo)
        if plc is None:
            raise ValueError(f"«{a.dispositivo}» no es un PLC con programa: «escribir» va a una variable de su "
                             f"programa; PLC: {', '.join(sorted(self.plcs)) or 'ninguno'}")
        fn = getattr(plc, "escribir", None)
        if not callable(fn):
            raise ValueError(f"el PLC externo {a.dispositivo} no admite «escribir»: su conector no trae "
                             "escribir(ruta, valor)")
        _, valor = escritura(plc.compilado, a.variable, a.valor)  # también antes de un PLC de afuera
        if plc.estado == SIN_TENSION:
            return f"{a.dispositivo} está sin tensión: no atiende la escritura de «{a.variable}»"
        fn(a.variable, valor)
        return None

    # ── eventos del mundo ───────────────────────────────────────────────────────────────────

    def _evento(self, e: Evento, reverso: bool) -> None:
        d = e.datos
        if e.tipo == "atasco":
            junta = d["junta"]
            juntas = self.juntas if self.acople is None else set(self.acople.integ.juntas)
            if self.acople is not None and junta in juntas:
                self.acople.atasco[self.acople.dof(junta)] = 0.0 if reverso else float(d["par_Nm"])
            elif juntas is not None and junta not in juntas:
                parecida = difflib.get_close_matches(junta, sorted(juntas), n=1)
                pista = f" ¿Quisiste decir «{parecida[0]}»?" if parecida else ""
                raise ValueError(f"atasco: la junta «{junta}» no está en la simulación.{pista} "
                                 f"Móviles: {', '.join(sorted(juntas)) or 'ninguna'}")
        elif e.tipo == "corte_de_fase":
            self.tab.red(d.get("red")).accionar("reponer_fase" if reverso else "perder_fase", d["fase"])
        elif e.tipo == "caida_de_red":
            self.tab.red(d.get("red")).accionar("caida", 1.0 if reverso else d["factor"])
        elif e.tipo == "cable_cortado":
            ramas = self.tab.ramas_de(d["rama"])
            if not ramas:
                raise ValueError(f"cable_cortado: «{d['rama']}» no es una rama de las redes (un conductor "
                                 "sin largo ni sección es una unión ideal y no se puede cortar: declara "
                                 "largo_m en add_wire o add_cable)")
            for red, rid in ramas:
                (red.reponer if reverso else red.cortar)(rid)
        elif e.tipo == "sensor_pegado":
            self._modelo(d["dispositivo"]).accionar("forzar", None if reverso else d["valor"])
        elif e.tipo == "falla":  # cosim-fallas D4: el reverso o `quitar` la reparan
            for h in fallas.aplicar(self.tab, d, reverso or bool(d.get("quitar"))):
                if h not in self.tab.hipotesis:
                    self.tab.hipotesis.append(h)
        elif e.tipo in ("corte_de_aire", "presion_de_red", "fuga"):  # V8.9 D8: la red de aire
            self._aire(e, reverso)

    def _aire(self, e: Evento, reverso: bool) -> None:
        aire, d = self.tab.aire, e.datos
        if aire is None:
            raise ValueError(f"{e.tipo}: el documento no tiene circuito de aire (add_device de un FRL, "
                             "válvulas y cilindros con sus add_tubo)")
        if e.tipo == "corte_de_aire":
            aire.p_red = aire.p_red_condicion if reverso else P_ATM_PA
        elif e.tipo == "presion_de_red":
            aire.p_red = aire.p_red_condicion if reverso else float(d["bar"]) * 1e5 + P_ATM_PA
        else:
            for h in aire.fuga(d["puerto"], d.get("C"), d.get("b"), reverso or bool(d.get("quitar"))):
                if h not in self.tab.hipotesis:
                    self.tab.hipotesis.append(h)


def _registro(a: Accion) -> dict:
    reg = {"accion": a.accion, "dispositivo": a.dispositivo}
    if a.variable is not None:
        reg["variable"] = a.variable
    if a.valor is not None:
        reg["valor"] = a.valor
    return reg


class _SinEscribir:
    """En `validar`, el PLC externo cuyo conector no trae `escribir`."""


def plcs_de_prueba(programas, externos: dict | None = None) -> dict:
    """Los PLC de `validar`: uno desechable por programa (con un PLC de afuera, el MISMO programa:
    la ruta y el tipo se validan igual) y, si el conector no trae `escribir`, uno que no escribe."""
    out: dict = {}
    for p in programas:
        clase = (externos or {}).get(p.plc, (None,))[0]
        if clase is not None and not callable(getattr(clase, "escribir", None)):
            out[p.plc] = _SinEscribir()
            continue
        try:
            out[p.plc] = PLC(p.compilado, ciclo_ms=p.ciclo_ms, ciclos=p.ciclos or None)
        except (KeyError, ValueError):  # los ciclos los rechaza la corrida; aquí sólo la memoria
            out[p.plc] = PLC(p.compilado)
    return out


def validar(esc, tablero, juntas: set, plcs: dict | None = None) -> None:
    """Corre la agenda entera sobre `tablero` y `plcs` (desechables): `EscenarioInvalido` con el
    motivo."""
    try:
        ag = Agenda(esc, tablero, None, juntas=juntas, plcs=plcs)
        ag.aplicar(float("inf"))
    except (ValueError, KeyError) as exc:
        if isinstance(exc, EscenarioInvalido):
            raise
        raise EscenarioInvalido(f"escenario: {exc}") from exc
