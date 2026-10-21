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
    «-Q3A») sigue al aparato cuya designación es la suya sin el sufijo de letras («-Q3»): a su
    bobina, a su protección o a su manija;
  - fuentes de la ficha → fuentes DC o AC (la red, `tipo: red`, va detrás de su impedancia; el
    resto es ideal); un aparato con varias fuentes las nombra «-T1.1», «-T1.2» (como el ERC);
  - cargas: bobina (su potencia de placa a Uc), piloto (Un/I), entrada (IEC 61131-2: ver
    `R_ENTRADA_*`), motor y alimentación en alterna (`potencia`: la da su modelo en cada paso);
    el potenciómetro de una botonera es una rama `potenciometro`;
  - conductores: la sección y el largo del conductor, o los de su CABLE si es un hilo de uno;
    sin largo, unión ideal.
Lo que no se puede emular sin inventar va en `hipotesis` (lo que se supuso) o `avisos`.
"""

from __future__ import annotations

import re

#: Entrada digital tipo 1 (IEC 61131-2): en ON debe tomar ≥ 2 mA a 15 V, es decir R ≤ 7,5 kΩ.
#: Se toma ese BORDE de la norma (criterio de diseño: la ficha no da la corriente de entrada).
R_ENTRADA_DIGITAL_OHM = 7500.0
#: Entrada analógica de tensión (IEC 61131-2): impedancia de entrada ≥ 10 kΩ; se toma el borde.
R_ENTRADA_ANALOGICA_OHM = 10000.0

_SUFIJO = re.compile(r"^(.*\d)[A-Za-z]+$")


def _punto(des: str, borne: str) -> str:
    return f"{des}:{borne}"


def _sistema_ac(t) -> str:
    if t.fases == 3:
        return "3F+N" if t.neutro else "3F"
    return "2F" if t.fases == 2 else "1F+N"


def _maestro(des: str, dispositivos: dict) -> str | None:
    m = _SUFIJO.match(des)
    return m.group(1) if m and m.group(1) in dispositivos else None


def _actuador_maestro(d) -> str | None:
    acciones = {(c.tipo, c.accion) for c in d.caminos}
    if any(a == "bobina" for _, a in acciones):
        return "bobina"
    if any(t == "proteccion" for t, _ in acciones):
        return "cerrado"
    if any(a == "mano" for _, a in acciones):
        return "mano"
    return None


class _Armado:
    def __init__(self, modelo, temperatura_C):
        from apolo.library.electrico.redes import resolver

        self._resolver = resolver
        self.modelo = modelo
        self.temperatura_C = temperatura_C
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
                maestro = _maestro(des, self.dispositivos)
                que = _actuador_maestro(self.dispositivos[maestro]) if maestro else None
                if que is None:
                    buscado = _SUFIJO.sub(r"\1", des)
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
            out["pe_a_neutro"] = d.modelo.get("esquema") == "TN"
            f_hz = t.frecuencia_hz[0] if t.frecuencia_hz else d.modelo.get("f_Hz")
            if f_hz:
                out["f_Hz"] = float(f_hz)
        self.fuentes.append(out)

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
        ideales = 0
        for i, cond in enumerate(self.modelo.conductores):
            pts = []
            for p in cond.puntos:
                r, motivo = self._resolver(p, self.dispositivos)
                if r is None:
                    self.avisos.append(f"conductor {i + 1} ({cond.etiqueta}): {motivo}")
                else:
                    pts.append(_punto(*r))
            if len(pts) < 2:
                continue
            # el hilo de un cable tiene la sección y el largo del CABLE (no puede ser otro)
            cable = cables.get(cond.cable) if cond.cable else None
            seccion = (cable.seccion_mm2 if cable and cable.seccion_mm2 else None) or cond.seccion_mm2
            largo = cable.largo_m if cable and cable.largo_m is not None else cond.largo_m
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
        if ideales:
            self.hipotesis.append(f"{ideales} conductor(es) sin largo o sección declarados: unión ideal, "
                                  "sin caída (declara largo_m en add_wire o add_cable)")

    def dict(self) -> dict:
        out = {"formato": 1, "ramas": self.ramas, "fuentes": self.fuentes, "cargas": self.cargas,
               "actuadores": self.actuadores, "hipotesis": self.hipotesis, "avisos": self.avisos}
        if self.temperatura_C is not None:
            out["temperatura_C"] = float(self.temperatura_C)
        return out


def entrada_red(modelo, *, temperatura_C: float | None = None) -> dict:
    """El formato plano de `apolo.cosim.red` para un `ModeloElectrico` evaluado."""
    a = _Armado(modelo, temperatura_C)
    for d in a.dispositivos.values():
        a.dispositivo(d)
    a.conductores()
    return a.dict()


def entrada_red_documento(doc, *, temperatura_C: float | None = None) -> dict:
    """`entrada_red` del modelo eléctrico del documento (`doc.electrico`; vacío sin carril)."""
    from .electrico import modelo

    return entrada_red(modelo(doc), temperatura_C=temperatura_C)
