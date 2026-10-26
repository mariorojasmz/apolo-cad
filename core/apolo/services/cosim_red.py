"""El modelo eléctrico evaluado de V8.1 → el formato PLANO de las redes de la co-simulación
(plan V8.3 F3).

`cosim/red` no importa `apolo.library` (el worker de F4 no carga el catálogo ni OCCT), así que la
traducción de los dataclasses (`Dispositivo`, `Conductor`, `Cable`) vive aquí, del lado del
proceso que tiene el documento; el resultado es un dict JSON-able que viaja en el snapshot de F4
y que `apolo.cosim.red.armar` lee. Este módulo NO importa `cosim`: produce datos, no redes.

Lo que traduce:
  - camino `fijo` → rama `union`; `NA`/`NC` → `contacto` movido por «<designación>.<actuador>»
    (`Camino.actuador`: el `grupo` o la acción); `proteccion` → `contacto` «<designación>.cerrado»
    («-F3.2.cerrado» en la unidad 2 de un portafusible). Un contacto `acople` (bloque auxiliar
    «-Q3A») sigue al aparato que dice su `acoplado_a` («-Q3»: la regla de
    `library/electrico/acoples.py`, que el carril aplica al cerrar el modelo; aquí sólo se LEE):
    a su bobina, a su protección o a su manija;
  - fuentes de la ficha → fuentes DC o AC (la red, `tipo: red`, va detrás de su impedancia; el
    resto es ideal); un aparato con varias fuentes las nombra «-T1.1», «-T1.2» (como el ERC);
  - cargas: bobina (su potencia de placa a Uc), piloto (Un/I), entrada (IEC 61131-2: ver
    `R_ENTRADA_*`), motor y alimentación en alterna (`potencia`: la da su modelo en cada paso);
    el potenciómetro de una botonera es una rama `potenciometro`;
  - conductores: la sección y el largo del conductor, o los de su CABLE si es un hilo de uno.
    El largo DECLARADO (`largo_m`) manda; sin él, el CALCULADO (`largos_calculados`, V8.5 F5b):
    el ruteado de un conductor dentro de un tablero armado y el del recorrido de un cable de
    campo con `por`, dicho en `hipotesis`. Sin ninguno, unión ideal.
Lo que no se puede emular sin inventar va en `hipotesis` (lo que se supuso) o `avisos`.
"""

from __future__ import annotations

#: Entrada digital tipo 1 (IEC 61131-2): en ON debe tomar ≥ 2 mA a 15 V, es decir R ≤ 7,5 kΩ.
#: Se toma ese BORDE de la norma (criterio de diseño: la ficha no da la corriente de entrada).
R_ENTRADA_DIGITAL_OHM = 7500.0
#: Entrada analógica de tensión (IEC 61131-2): impedancia de entrada ≥ 10 kΩ; se toma el borde.
R_ENTRADA_ANALOGICA_OHM = 10000.0

def _punto(des: str, borne: str) -> str:
    return f"{des}:{borne}"


def _sistema_ac(t) -> str:
    if t.fases == 3:
        return "3F+N" if t.neutro else "3F"
    return "2F" if t.fases == 2 else "1F+N"


class _Armado:
    def __init__(self, modelo, temperatura_C, largos=None):
        from apolo.library.electrico import acoples
        from apolo.library.electrico.redes import nombre_conductor, resolver

        self._resolver = resolver
        self._nombre = nombre_conductor
        self._acoples = acoples
        self.modelo = modelo
        self.temperatura_C = temperatura_C
        self.largos = largos or {}
        self.dispositivos: dict = {}
        for d in modelo.dispositivos:
            self.dispositivos.setdefault(d.designacion, d)
        self.ramas: list[dict] = []
        self.fuentes: list[dict] = []
        self.cargas: list[dict] = []
        self.actuadores: dict = {}
        self.hipotesis: list[str] = []
        self.avisos: list[str] = []
        self._ids: set[str] = set()

    def _id(self, base: str) -> str:
        rid, k = base, 2
        while rid in self._ids:
            rid, k = f"{base}#{k}", k + 1
        self._ids.add(rid)
        return rid

    # ── dispositivos ────────────────────────────────────────────────────────────────────────

    def dispositivo(self, d) -> None:
        des = d.designacion
        for c in d.caminos:
            de, a = _punto(des, c.de), _punto(des, c.a)
            rid = self._id(f"{des}:{c.de}-{c.a}")
            if c.tipo == "fijo":
                self.ramas.append({"id": rid, "tipo": "union", "de": de, "a": a, "dispositivo": des})
                continue
            if c.tipo == "proteccion":
                unidad = c.de.split(".")[0] if d.bornera and "." in c.de else None
                act = f"{des}.{unidad}.cerrado" if unidad else f"{des}.cerrado"
                self.actuadores.setdefault(act, True)
            elif c.accion == "acople":
                maestro = d.acoplado_a  # D4: lo puso el carril (`acoples.cerrar_acoples`)
                aparato = self.dispositivos.get(maestro) if maestro else None
                que = self._acoples.actuador_maestro(aparato) if aparato is not None else None
                if que is None:
                    buscado = self._acoples.maestro_buscado(des)
                    self.avisos.append(f"{des}: contacto auxiliar sin aparato que lo mueva (se busca "
                                       f"«{buscado}»); queda en reposo")
                    act = f"{des}.acople"
                else:
                    act = f"{maestro}.{que}"
                self.actuadores.setdefault(act, que == "cerrado" or (que == "mano" and self._cerrado_inicial(maestro)))
            else:
                act = f"{des}.{c.actuador}"
                self.actuadores.setdefault(act, c.accion == "mano" and self._cerrado_inicial(des))
            self.ramas.append({"id": rid, "tipo": "contacto", "de": de, "a": a, "contacto":
                               "proteccion" if c.tipo == "proteccion" else c.tipo, "actuador": act,
                               "dispositivo": des})
        for k, f in enumerate(d.fuentes):
            self._fuente(d, f, des if len(d.fuentes) == 1 else f"{des}.{k + 1}")
        for c in d.cargas:
            self._carga(d, c)

    def _cerrado_inicial(self, des: str) -> bool:
        """Un seccionador arranca CERRADO (la máquina en servicio, como su modelo); el resto de
        los mandos, en reposo. El llamador da luego el estado de sus modelos."""
        d = self.dispositivos.get(des)
        return bool(d and d.modelo.get("tipo") == "seccionador")

    def _fuente(self, d, f, fid: str) -> None:
        t = f.tension
        polos = {_punto(d.designacion, b): p for b, p in f.polos}
        if t.tipo not in ("DC", "AC") or t.linea is None:
            self.avisos.append(f"fuente {fid}: «{t}» no es una tensión fija de continua o alterna; no se simula")
            return
        out = {"id": fid, "tipo": t.tipo, "polos": polos, "U_V": t.linea, "dispositivo": d.designacion,
               "ideal": d.modelo.get("tipo") != "red"}
        if t.tipo == "AC":
            out["sistema"] = _sistema_ac(t)
            self._tierra(d, fid, out)
            f_hz = t.frecuencia_hz[0] if t.frecuencia_hz else d.modelo.get("f_Hz")
            if f_hz:
                out["f_Hz"] = float(f_hz)
        self.fuentes.append(out)

    def _tierra(self, d, fid: str, out: dict) -> None:
        """El PE de una fuente de alterna según el esquema de tierra, del AJUSTE primero y luego
        de la ficha (plan datos-de-corte-y-acometida, D7): TN/TN-S/TN-C-S → el PE es la tierra
        (`pe_a_neutro`); TT con `RA_ohm` → el PE unido a tierra por 1/RA (`R_tierra_ohm`); TT sin
        RA o IT → fuera de la potencia. Sin esquema, lo de siempre (sin claves nuevas)."""
        from apolo.library.electrico.acometida import HIPOTESIS_RA, PE_ES_TIERRA, esquema_de, ra_de

        esquema = esquema_de(d.modelo, d.ajustes) if d.modelo.get("tipo") == "red" else None
        out["pe_a_neutro"] = esquema in PE_ES_TIERRA
        if esquema is None:
            return
        out["esquema"] = esquema
        ra = ra_de(d.modelo, d.ajustes)
        if esquema == "TT" and ra is not None:
            out["R_tierra_ohm"] = float(ra)
            self.hipotesis.append(f"{fid}: TT con RA_ohm = {ra:g} Ω; {HIPOTESIS_RA}")
        elif esquema == "TT":
            self.avisos.append(f"{fid}: red TT sin RA_ohm: el PE queda fuera de la potencia y una falla "
                               "a masa no se simula (declara RA_ohm en add_device.ajustes)")

    def _carga(self, d, c) -> None:
        des, m = d.designacion, d.modelo
        bornes = [_punto(des, b) for b in c.bornes]
        cid = self._id(f"{des}:{'-'.join(c.bornes)}")
        out = {"id": cid, "tipo": c.tipo, "bornes": bornes, "dispositivo": des}
        t = c.tension
        if c.tipo == "bobina" and m.get("Uc_V"):
            out.update(modo="impedancia", Un_V=float(m["Uc_V"]))
            if m.get("bobina_W"):
                out["S_VA"] = float(m["bobina_W"])
            elif isinstance(m.get("bobina_VA"), dict) and m["bobina_VA"].get("mantenimiento"):
                out["S_VA"] = float(m["bobina_VA"]["mantenimiento"])
                self.hipotesis.append(f"{des}: bobina de alterna con su potencia de MANTENIMIENTO y fp 1; la "
                                      "de llamada mientras cierra la pone el llamador (`cargas`)")
            else:
                out["modo"] = "ninguna"
                self.avisos.append(f"{des}: la bobina no declara su consumo; no carga la red")
        elif c.tipo == "piloto" and m.get("Un_V") and m.get("I_mA"):
            out.update(modo="impedancia", R_ohm=float(m["Un_V"]) / (float(m["I_mA"]) / 1000.0))
        elif c.tipo == "entrada":
            analogica = t.rango is not None
            R = m.get("R_entrada_ohm") or (R_ENTRADA_ANALOGICA_OHM if analogica else R_ENTRADA_DIGITAL_OHM)
            out.update(modo="impedancia", R_ohm=float(R))
        elif c.tipo in ("motor", "alimentacion") and t.tipo == "AC":
            out.update(modo="potencia")
        elif c.tipo == "otra" and m.get("potenciometro_ohm") and len(c.bornes) == 2:
            self._potenciometro(d, c)
            return
        else:
            out["modo"] = "ninguna"
            self.hipotesis.append(f"{des}: la carga {'-'.join(c.bornes)} ({c.tipo}, {t}) no declara su "
                                  "consumo en el catálogo: no carga la red (cota optimista)")
        self.cargas.append(out)

    def _potenciometro(self, d, c) -> None:
        des = d.designacion
        extremos = set(c.bornes)
        cursor = next((b.id for b in d.bornes if b.rol == "señal" and b.id not in extremos), None)
        if cursor is None:
            self.avisos.append(f"{des}: el potenciómetro no tiene borne de cursor; no se simula")
            return
        act = f"{des}.potenciometro"
        self.actuadores.setdefault(act, 0.5)
        self.ramas.append({"id": self._id(f"{des}:potenciometro"), "tipo": "potenciometro",
                           "de": _punto(des, c.bornes[0]), "cursor": _punto(des, cursor),
                           "a": _punto(des, c.bornes[1]), "R_ohm": float(d.modelo["potenciometro_ohm"]),
                           "actuador": act, "dispositivo": des})

    # ── conductores ─────────────────────────────────────────────────────────────────────────

    def conductores(self) -> None:
        cables = {c.designacion: c for c in self.modelo.cables}
        por_cond = self.largos.get("conductores") or {}
        por_cable = self.largos.get("cables") or {}
        ideales = 0
        calc_cond: set[str] = set()
        calc_cable: set[str] = set()
        for i, cond in enumerate(self.modelo.conductores):
            pts = []
            for p in cond.puntos:
                r, motivo = self._resolver(p, self.dispositivos)
                if r is None:
                    self.avisos.append(f"conductor {self._nombre(cond)}: {motivo}")  # nunca su índice
                else:
                    pts.append(_punto(*r))
            if len(pts) < 2:
                continue
            # el hilo de un cable tiene la sección y el largo del CABLE (no puede ser otro)
            cable = cables.get(cond.cable) if cond.cable else None
            seccion = (cable.seccion_mm2 if cable and cable.seccion_mm2 else None) or cond.seccion_mm2
            largo = cable.largo_m if cable and cable.largo_m is not None else cond.largo_m
            if largo is None and cable is not None and por_cable.get(cable.id) is not None:
                largo = por_cable[cable.id]  # el recorrido del cable de campo (F4)
                calc_cable.add(cable.designacion)
            elif largo is None and cable is None and por_cond.get(cond.id) is not None:
                largo = por_cond[cond.id]  # el ruteado dentro del tablero armado (F2)
                calc_cond.add(cond.id)
            base = f"{cond.cable}.{cond.hilo}" if cond.cable else (cond.id or f"conductor {i + 1}")
            tramos = list(zip(pts, pts[1:]))
            ideal = cond.tipo == "puente" or not seccion or largo is None
            ideales += bool(ideal and cond.tipo != "puente")
            for k, (a, b) in enumerate(tramos):
                rid = self._id(base if len(tramos) == 1 else f"{base}#{k + 1}")
                if ideal:
                    self.ramas.append({"id": rid, "tipo": "union", "de": a, "a": b})
                else:
                    self.ramas.append({"id": rid, "tipo": "conductor", "de": a, "a": b,
                                       "seccion_mm2": float(seccion), "largo_m": float(largo) / len(tramos)})
        if calc_cond:
            self.hipotesis.append(f"{len(calc_cond)} conductor(es) del tablero sin largo declarado: se toma "
                                  "el largo ruteado por las canaletas (layout_tablero); si lo mediste, "
                                  "declara largo_m en add_wire")
        if calc_cable:
            self.hipotesis.append(f"cable(s) {', '.join(sorted(calc_cable))} sin largo declarado: se toma el "
                                  "largo calculado de su recorrido (add_cable.por); si lo mediste, declara "
                                  "largo_m en add_cable")
        if ideales:
            self.hipotesis.append(f"{ideales} conductor(es) sin largo o sección declarados: unión ideal, "
                                  "sin caída (declara largo_m en add_wire o add_cable)")

    def dict(self) -> dict:
        out = {"formato": 1, "ramas": self.ramas, "fuentes": self.fuentes, "cargas": self.cargas,
               "actuadores": self.actuadores, "hipotesis": self.hipotesis, "avisos": self.avisos}
        if self.temperatura_C is not None:
            out["temperatura_C"] = float(self.temperatura_C)
        return out


def entrada_red(modelo, *, temperatura_C: float | None = None, largos: dict | None = None) -> dict:
    """El formato plano de `apolo.cosim.red` para un `ModeloElectrico` evaluado. `largos` =
    `largos_calculados` del documento (sin él, sólo los declarados: lo de siempre)."""
    a = _Armado(modelo, temperatura_C, largos)
    for d in a.dispositivos.values():
        a.dispositivo(d)
    a.conductores()
    return a.dict()


def largos_calculados(doc, m=None) -> dict:
    """`{"conductores": {id: m}, "cables": {id del add_cable: m}}`: los largos que el documento
    CALCULA para lo que no declara `largo_m` (V8.5 F5b), de las mismas cuentas que la BOM: el ruteo
    del tablero armado (`tablero.largos`) y el recorrido de los cables de campo con `por`
    (`cables_campo.largos`). Vacío sin tablero armado ni `por` (la red de siempre); si el ruteo no
    se puede armar, vacío también (la red sigue con sus uniones ideales, dichas en la hipótesis)."""
    from apolo.commands.errors import CommandError

    from . import cables_campo
    from .electrico import modelo
    from .tablero import largos, ruteos

    m = m if m is not None else modelo(doc)
    try:
        tableros = ruteos(doc, m)
        cables = cables_campo.largos(cables_campo.recorridos(doc, m, tableros))
    except (CommandError, ValueError):
        return {}
    return {k: v for k, v in (("conductores", largos(tableros)), ("cables", cables)) if v}


def entrada_red_documento(doc, *, temperatura_C: float | None = None) -> dict:
    """`entrada_red` del modelo eléctrico del documento (`doc.electrico`; vacío sin carril), con
    sus largos calculados."""
    from .electrico import modelo

    m = modelo(doc)
    return entrada_red(m, temperatura_C=temperatura_C, largos=largos_calculados(doc, m))
