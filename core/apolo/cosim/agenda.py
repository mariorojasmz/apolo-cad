"""La agenda del escenario: condiciones iniciales, acciones del operador y eventos del mundo
(plan V8.3 D12), aplicados con el reloj virtual.

Cada acción o evento se aplica en el PRIMER intercambio con t ≥ su hora; uno con `duracion_s`
agenda su reverso. Lo aplicado queda en `eventos` con la hora real y la programada: son las
anclas de las aserciones «dentro_de Δ desde <acción o evento>» (F5).

`validar` corre la agenda entera sobre un tablero DESECHABLE antes de simular: un dispositivo
que no existe, una acción que no admite o una rama que no se puede cortar es error accionable en
el snapshot, no a mitad de la co-simulación.
"""

from __future__ import annotations

import difflib

from .escenario import Accion, EscenarioInvalido, Evento

EPS_T = 1e-9


class Agenda:
    def __init__(self, esc, tablero, acople=None, *, juntas: set | None = None):
        self.esc, self.tab, self.acople = esc, tablero, acople
        self.juntas = juntas
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
                self._accion(x)
                reg = {"accion": x.accion, "dispositivo": x.dispositivo}
                if x.valor is not None:
                    reg["valor"] = x.valor
            else:
                self._evento(x, reverso)
                reg = {"evento": x.tipo + (".fin" if reverso else ""), **x.datos}
            self.eventos.append({"t": round(t, 6), "programado_s": round(t_prog, 6), **reg})

    def _aplicar_inyectada(self, t: float, t_prog: float, seq: int, x) -> None:
        ident = self._inyectadas.pop(seq)
        try:
            if isinstance(x, Accion):
                self._accion(x)
                reg = {"accion": x.accion, "dispositivo": x.dispositivo}
                if x.valor is not None:
                    reg["valor"] = x.valor
            else:
                self._evento(x, False)
                reg = {"evento": x.tipo, **x.datos}
        except (ValueError, KeyError) as exc:
            if isinstance(x, Evento) and x.duracion_s:  # sin el evento, su reverso tampoco
                self.items = [it for it in self.items if not (it[2] is x and it[3])]
            self.respuestas.append({"id": ident, "ok": False, "motivo": str(exc).strip("'\"")})
            return
        self.eventos.append({"t": round(t, 6), "programado_s": round(t_prog, 6), **reg})
        self.respuestas.append({"id": ident, "ok": True, "t": round(t, 6)})

    # ── acciones del operador ───────────────────────────────────────────────────────────────

    def _accion(self, a: Accion) -> None:
        m = self._modelo(a.dispositivo)
        valor = a.valor
        if a.accion in ("pulsar", "soltar") and (a.actuador or a.durante_s is not None):
            valor = {"actuador": a.actuador, "durante_s": a.durante_s}
        if a.accion not in m.ACCIONES:
            raise ValueError(f"{a.dispositivo} ({m.ref}, {m.tipo}) no admite «{a.accion}»; "
                             f"acciones: {', '.join(m.ACCIONES) or '(ninguna)'}")
        m.accionar(a.accion, valor)

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


def validar(esc, tablero, juntas: set) -> None:
    """Corre la agenda entera sobre `tablero` (desechable): `EscenarioInvalido` con el motivo."""
    try:
        ag = Agenda(esc, tablero, None, juntas=juntas)
        ag.aplicar(float("inf"))
    except (ValueError, KeyError) as exc:
        if isinstance(exc, EscenarioInvalido):
            raise
        raise EscenarioInvalido(f"escenario: {exc}") from exc
