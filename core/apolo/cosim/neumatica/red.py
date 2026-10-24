"""El circuito de aire en la co-simulación: topología y paso (plan V8.9 D3, D4, D8).

`RedAire(aire, dispositivos, modelos)` lee los tubos del carril (`aire["tubos"]`, «-QM1:4» →
«-MM1:A», con su Ø interior y su largo) y arma, para cada cámara de cada cilindro, la CADENA que
la une a su válvula: los tubos (su volumen se suma a la cámara) y los reguladores de caudal en
línea (orificios con un C por sentido: `caudal` en el libre 1→2 y el AJUSTE `C_regulado` en el
2→1). En cada intercambio la válvula, en su posición, une la cámara a:
  - la ALIMENTACIÓN (vía 1): aguas arriba, la válvula de corte (abierta: su C; cerrada con
    escape: la línea se descarga por ella a la atmósfera) y el FRL (fuente a su regulada detrás de
    su C), o la toma directa a la presión de red si no hay FRL;
  - el ESCAPE (3/5): la atmósfera, por la vía de escape de la válvula y lo que cuelgue de ese
    puerto (silenciador o regulador de caudal), o libre;
  - nada (bloqueada).
Cada camino es UNA conductancia equivalente por sentido (`orificio.serie`, aproximación
declarada) desde una presión fija. Lo que no se modela: el volumen de la línea de alimentación
(la caída del FRL se cuenta por cada válvula como si la alimentara sola: `HIPOTESIS_LINEA`), las
ondas de presión y la temperatura del aire (D3, «Lo que este plan NO hace»).

Eventos (D8, por la agenda): `corte_de_aire` (la toma a la presión atmosférica), `presion_de_red`
(otra presión desde t) y `fuga` (un orificio a la atmósfera en un puerto de una cámara).

Puro: `cosim.modelos` y `cosim.neumatica`.
"""

from __future__ import annotations

import difflib
import math

from ..modelos.base import ModeloIncompleto
from ..modelos.electrovalvula import Electrovalvula
from .camara import HIPOTESIS_N, HIPOTESIS_TUBOS, Camino
from .cilindro import Cilindro
from .componentes import HIPOTESIS_FRL, Frl, Toma, ValvulaCorte
from .orificio import B_TOBERA, HIPOTESIS_ATM, HIPOTESIS_SERIE, M_ELIPTICO, P_ATM_PA, serie
from .valvula import HIPOTESIS_ESCAPE, conexion, puertos_trabajo

_BAR = 1e5
HIPOTESIS_LINEA = ("la línea de alimentación no tiene volumen propio: la caída del FRL y del corte "
                   "se cuenta por cada válvula como si la alimentara sola")
HIPOTESIS_ARRANQUE = ("al empezar, cada cámara está a la presión de lo que su válvula en reposo le une "
                      "(la máquina ya con aire)")


def _via(d: dict, clave: str) -> tuple | None:
    c = (d or {}).get(clave)
    return None if not c else (float(c["C"]), float(c["b"]), float(c.get("m", M_ELIPTICO)))


class _Lineas:
    """Los puertos unidos por tubos (unión-búsqueda) y el volumen de tubo de cada línea."""

    def __init__(self, tubos: list):
        self.padre: dict = {}
        self.volumen: dict = {}
        self.sin_largo: list = []
        for t in tubos:
            a, b = self._raiz(t["desde"]), self._raiz(t["hasta"])
            if a != b:
                self.padre[a] = b
                self.volumen[b] = self.volumen.get(b, 0.0) + self.volumen.pop(a, 0.0)
            largo, D = t.get("largo_m"), t.get("D_int_mm")
            if largo is None or D is None:
                self.sin_largo.append(f"{t['desde']} → {t['hasta']}")
                continue
            r = self._raiz(t["desde"])
            self.volumen[r] = self.volumen.get(r, 0.0) + math.pi * (D / 1000.0) ** 2 / 4.0 * float(largo)

    def _raiz(self, p: str) -> str:
        while self.padre.get(p, p) != p:
            p = self.padre[p]
        return p

    def otros(self, puerto: str) -> list[str]:
        """Los demás puertos de la línea de `puerto` (vacío si no tiene tubo)."""
        r = self._raiz(puerto)
        todos = set(self.padre) | set(self.padre.values())
        return sorted(p for p in todos if p != puerto and self._raiz(p) == r)

    def volumen_de(self, puerto: str) -> float:
        return self.volumen.get(self._raiz(puerto), 0.0)


class _Camara:
    def __init__(self, cil: str, lado: str):
        self.cil, self.lado = cil, lado
        self.valvula: Electrovalvula | None = None
        self.via_valvula = None             # puerto de trabajo de la válvula
        self.ida: list = []                 # vías válvula → cámara (reguladores en línea)
        self.vuelta: list = []              # vías cámara → válvula
        self.volumen = 0.0
        self.puertos: set = set()           # los puertos de su cadena (para las fugas)
        self.fugas: dict = {}
        self.clave = None                   # lo que decidió `vigentes` (`RedAire.caminos`)
        self.vigentes: list = []


class RedAire:
    def __init__(self, aire: dict, dispositivos: list, modelos: dict):
        self.modelos = modelos
        self.fichas = {d.designacion: (d.modelo or {}).get("aire") or {} for d in dispositivos}
        self.ajustes = {d.designacion: d.ajustes or {} for d in dispositivos}
        self.lineas = _Lineas(aire.get("tubos") or [])
        self.p_red = float(aire.get("presion_red_bar", 0.0)) * _BAR + P_ATM_PA
        self.p_red_condicion = self.p_red
        self.hipotesis: list[str] = [HIPOTESIS_ATM, HIPOTESIS_N, HIPOTESIS_TUBOS, HIPOTESIS_SERIE, HIPOTESIS_LINEA,
                                     HIPOTESIS_ARRANQUE]
        self.toma_directa = Toma()
        self._arriba: dict = {}
        self._escapes: dict = {}
        self.cilindros = [(des, m) for des, m in modelos.items() if isinstance(m, Cilindro)]
        self.camaras: dict = {}
        for des, cil in self.cilindros:
            for lado in ("A", "B"):
                self.camaras[(des, lado)] = self._camara(des, lado)
            cil.V_tubo_A, cil.V_tubo_B = self.camaras[(des, "A")].volumen, self.camaras[(des, "B")].volumen
        for cam in self.camaras.values():  # todo lo que la corrida va a pedir, validado al armar
            v = cam.valvula
            self._aguas_arriba(f"{v.designacion}:1")
            for via in (("3", "5") if v.vias == 5 else ("3",) if v.vias == 3 else ()):
                self._escape(v, via)
        if self.lineas.sin_largo:
            self.hipotesis.append(f"tubos sin largo (sin volumen en la cámara): {', '.join(self.lineas.sin_largo)}")
        self.frls = [m for m in modelos.values() if isinstance(m, Frl)]
        if self.frls:
            self.hipotesis.append(HIPOTESIS_FRL)
        for des, cil in self.cilindros:
            p0 = [self._fuente(self.camaras[(des, "A")]), self._fuente(self.camaras[(des, "B")])]
            trabajo = max((c.p for c in p0 if c is not None), default=self.p_red)
            cil.friccion_junta_N = cil.sellos_N(trabajo)
            cil.pA = p0[0].p if p0[0] is not None else P_ATM_PA
            cil.pB = p0[1].p if p0[1] is not None else P_ATM_PA

    # ── topología ────────────────────────────────────────────────────────────────────────────

    def _tipo(self, des: str) -> str | None:
        return self.fichas.get(des, {}).get("tipo")

    def _camara(self, des: str, lado: str) -> _Camara:
        cam = _Camara(des, lado)
        puerto = f"{des}:{lado}"
        actual, visto = puerto, {puerto}
        while True:
            cam.puertos.add(actual)
            cam.volumen += self.lineas.volumen_de(actual)   # cada línea de la cadena, una vez
            otros = [p for p in self.lineas.otros(actual) if p not in visto]
            if not otros:
                raise ModeloIncompleto(f"{actual}: la cámara {lado} de {des} no llega a ninguna válvula por tubos "
                                       f"(add_tubo desde un puerto de trabajo de la válvula hasta {puerto})")
            if len(otros) > 1:
                raise ModeloIncompleto(f"{actual}: la línea une {', '.join(otros)}; la co-simulación de V8.9 simula "
                                       "una cámara por línea (de la válvula, o de un regulador en línea, al cilindro)")
            otro = otros[0]
            visto.add(otro)
            cam.puertos.add(otro)
            odes, opuerto = otro.rsplit(":", 1)
            m = self.modelos.get(odes)
            if isinstance(m, Electrovalvula):
                if opuerto not in puertos_trabajo(m.vias):
                    raise ModeloIncompleto(f"{otro}: la cámara {lado} de {des} llega a la vía {opuerto} de {odes}; "
                                           f"los puertos de trabajo son {', '.join(puertos_trabajo(m.vias))}")
                cam.valvula, cam.via_valvula = m, opuerto
                return cam
            if self._tipo(odes) == "regulador_caudal":
                libre, regulada = self._regulador(odes)
                sale = "1" if opuerto == "2" else "2"
                # caminando del cilindro hacia la válvula: entrar por 2 = válvula→cámara es 1→2 (libre)
                cam.ida.append(libre if opuerto == "2" else regulada)
                cam.vuelta.append(regulada if opuerto == "2" else libre)
                actual = f"{odes}:{sale}"
                visto.add(actual)
                continue
            raise ModeloIncompleto(f"{otro}: entre la cámara {lado} de {des} y su válvula hay un {self._tipo(odes) or odes} "
                                   "que la co-simulación no sabe poner en línea (válvula o regulador de caudal)")

    def _regulador(self, des: str) -> tuple:
        f = self.fichas[des]
        libre = _via(f, "caudal")
        aj = self.ajustes.get(des, {})
        if "C_regulado" not in aj:
            lo, hi = f.get("C_regulado", [0, 0])
            raise ModeloIncompleto(f"{des}: falta el ajuste «C_regulado» (entre {lo:g} y {hi:g}): lo fija el instalador "
                                   f"con el tornillo; decláralo en add_device.ajustes, p. ej. {{\"C_regulado\": {(lo + hi) / 2:g}}}")
        b = float(f.get("b_regulado", libre[1]))
        return libre, (float(aj["C_regulado"]), b, libre[2])

    def _aguas_arriba(self, puerto: str) -> tuple[list, object]:
        """([válvulas de corte], FRL o None) desde la vía 1 de una válvula hacia la toma (una vez
        por válvula: la topología no cambia en la corrida)."""
        hecho = self._arriba.get(puerto)
        if hecho is None:
            hecho = self._arriba[puerto] = self._buscar_arriba(puerto)
        return hecho

    def _buscar_arriba(self, puerto: str) -> tuple[list, object]:
        actual = puerto
        cortes: list = []
        for _ in range(16):
            hallado = None
            for o in self.lineas.otros(actual):
                odes, op = o.rsplit(":", 1)
                m = self.modelos.get(odes)
                if isinstance(m, Frl) and op == "2":
                    return cortes, m
                if isinstance(m, ValvulaCorte) and op == "2":
                    hallado = (m, f"{odes}:1")
            if hallado is None:
                break
            cortes.append(hallado[0])
            actual = hallado[1]
        return cortes, None

    def _escape(self, valvula: Electrovalvula, via: str) -> tuple[list, list]:
        """(vías válvula → atmósfera, vías atmósfera → válvula) por la vía de escape `via`."""
        clave = (valvula.designacion, via)
        hecho = self._escapes.get(clave)
        if hecho is None:
            hecho = self._escapes[clave] = self._buscar_escape(valvula, via)
        return hecho

    def _buscar_escape(self, valvula: Electrovalvula, via: str) -> tuple[list, list]:
        des = valvula.designacion
        e = _via(valvula.aire, "escape")
        if e is None:
            e = _via(valvula.aire, "caudal")
            texto = f"{des}: {HIPOTESIS_ESCAPE}"
            if texto not in self.hipotesis:
                self.hipotesis.append(texto)
        sale, entra = [e], [e]
        for o in self.lineas.otros(f"{des}:{via}"):
            odes, op = o.rsplit(":", 1)
            tipo = self._tipo(odes)
            if tipo == "silenciador":
                s = _via(self.fichas[odes], "caudal")
                sale.append(s)
                entra.append(s)
            elif tipo == "regulador_caudal":
                libre, regulada = self._regulador(odes)
                sale.append(libre if op == "1" else regulada)   # de la válvula hacia afuera: 1→2 libre
                entra.append(regulada if op == "1" else libre)
        return sale, entra

    # ── el paso ──────────────────────────────────────────────────────────────────────────────

    def _fuente(self, cam: _Camara) -> Camino | None:
        """El camino de la cámara en este instante, o None si la válvula la bloquea."""
        v = cam.valvula
        hacia = conexion(v, cam.via_valvula)
        if hacia is None:
            return None
        if hacia != "1":
            sale, entra = self._escape(v, hacia)
            return Camino(P_ATM_PA, serie(entra + cam.ida), serie(sale + cam.vuelta))
        vias = [_via(v.aire, "caudal")]
        cortes, frl = self._aguas_arriba(f"{v.designacion}:1")
        for c in cortes:
            vias.append(c.via)
            if not c.abierta:
                if not c.con_escape:
                    return None
                return Camino(P_ATM_PA, serie(vias + cam.ida), serie(vias + cam.vuelta))
        if frl is not None:
            frl.p_red = self.p_red
            vias.append(frl.via)
            return Camino(frl.p_salida, serie(vias + cam.ida), serie(vias + cam.vuelta), frl.toma)
        return Camino(self.p_red, serie(vias + cam.ida), serie(vias + cam.vuelta), self.toma_directa)

    def caminos(self, cam: _Camara) -> list:
        """Los caminos de la cámara; se rehacen sólo si cambió algo que los decide (la posición
        de la válvula, un corte, la presión de red o una fuga)."""
        cortes, _ = self._aguas_arriba(f"{cam.valvula.designacion}:1")
        clave = (cam.valvula.posicion, tuple(c.abierta for c in cortes), self.p_red, tuple(cam.fugas.items()))
        if clave != cam.clave:
            c = self._fuente(cam)
            cam.vigentes = ([c] if c is not None else []) + [Camino(P_ATM_PA, via, via) for via in cam.fugas.values()]
            cam.clave = clave
        return cam.vigentes

    def paso(self, dt: float, lecturas: dict) -> dict:
        """{cilindro: fuerza media (N)} del intercambio que viene, desde {cilindro: (x, v)} en m
        y m/s leídos de MuJoCo (D4)."""
        out = {}
        for des, cil in self.cilindros:
            x, v = lecturas[des]
            out[des] = cil.intercambio(dt, x, v, self.caminos(self.camaras[(des, "A")]),
                                       self.caminos(self.camaras[(des, "B")]))
        for m in self.frls:
            m.p_red = self.p_red
            m.toma.cerrar(dt)
        self.toma_directa.cerrar(dt)
        return out

    # ── eventos (D8) ─────────────────────────────────────────────────────────────────────────

    def camara_de(self, puerto: str) -> _Camara:
        for cam in self.camaras.values():
            if puerto in cam.puertos:
                return cam
        todos = sorted(p for cam in self.camaras.values() for p in cam.puertos)
        parecida = difflib.get_close_matches(puerto, todos, n=1)
        pista = f" ¿Quisiste decir «{parecida[0]}»?" if parecida else ""
        raise ValueError(f"fuga: «{puerto}» no es un puerto de la cámara de un cilindro.{pista} La fuga va en un "
                         f"puerto entre una válvula y un cilindro: {', '.join(todos) or 'ninguno'}")

    def fuga(self, puerto: str, C: float | None, b: float | None, quitar: bool) -> list[str]:
        cam = self.camara_de(puerto)
        if quitar:
            cam.fugas.pop(puerto, None)
            return []
        if not C or C <= 0:
            raise ValueError("fuga: «C» (dm³/(s·bar), ISO 6358) > 0 del orificio a la atmósfera")
        cam.fugas[puerto] = (float(C), B_TOBERA if b is None else float(b), M_ELIPTICO)
        return [] if b is not None else [f"fuga en {puerto}: b = {B_TOBERA:.3f} de una tobera ideal (k = 1,4)"]
