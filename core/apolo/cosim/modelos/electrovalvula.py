"""La electroválvula: sus bobinas mueven el carrete (plan V8.9 D6, D7; F3).

Eléctricamente cada bobina es la de un relé (D6): cierra con U ≥ `U_cierre_pct`·Uc y suelta con
U < `U_caida_pct`·Uc, con histéresis entre los dos. Las cifras van en `electrico.modelo` de la ref
(`tipo: electrovalvula`, `Uc_V`, `Uc`, `U_cierre_pct`, `U_caida_pct`, `bobina_W`); lo neumático
(vías, posiciones, mando, tiempos de conmutación, caudal) llega en `modelo["aire"]`, la ficha
`neumatico:` plana que arma el snapshot (`services/cosim_aire.py`).

El carrete, por su `mando` (ISO 5599-3: la bobina 14 conecta 1→4, la 12 conecta 1→2):
  - 5/2 monoestable: la 14 lo lleva a «14»; sin ella el muelle lo vuelve a «12»;
  - 5/2 biestable: la 14 a «14», la 12 a «12»; sin tensión (o con las dos) CONSERVA la posición;
    arranca en «12» (hipótesis declarada: el cilindro retraído);
  - 5/3 (centro cerrado, a escape o a presión): una bobina lo lleva a su lado; sin ninguna, los
    muelles lo centran en «0»; con las dos conserva la posición;
  - 3/2 (y 2/2) monoestable: la 12 lo lleva a «12»; sin ella vuelve a «0» (su `reposo` NC o NA).
Conmuta de UNA vez al cumplirse `t_on_ms` (hacia el lado de una bobina energizada) o `t_off_ms`
(lo que hace el muelle) de la ficha; si la orden se va antes, no conmuta.

El tablero indexa las bobinas por `BOBINAS` ({lado: primer borne}: «A1» con una bobina, «14A1» y
«12A1» con dos), sin rama propia (el patrón de `BORNES_ENTRADA` del relé de seguridad).

Señales (D7): `-QM1.posicion` («14», «12» o «0»), `-QM1.bobina14`, `-QM1.bobina12` (las que tiene).
Acción: `accionar_manual` con el lado («14», «12») — el accionamiento manual auxiliar ENCLAVADO
(se queda hasta `accionar_manual` «0») — sólo si la ficha lo trae (`manual: true`).
Fallas (cosim-fallas D2): `pegada` (el carrete no se mueve; en la posición pedida o en la que
está) y `bobina_cortada` (la bobina no ve tensión ni consume: el tablero la saca de la red; con
dos, la del canal pedido).
"""

from __future__ import annotations

from .base import EPS_T, Modelo, ModeloIncompleto, Parametros, magnitud

HIPOTESIS_CARRETE = "el carrete conmuta de una vez al cumplirse t_on / t_off de la ficha (sin tránsito)"


class Electrovalvula(Modelo):
    tipo = "electrovalvula"
    ACCIONES = ("accionar_manual",)
    #: la de dos bobinas pide el canal de la cortada; la de una, nada (`__init__`)
    FALLAS = {"pegada": "posicion?", "bobina_cortada": "canal"}

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.Uc = p.num("Uc_V", "tensión asignada de la bobina", positivo=True)
        p.texto("Uc", "tipo de la bobina", ("DC", "AC", "UC"))
        self.u_cierre = p.num("U_cierre_pct", "tensión de conmutación en % de Uc", positivo=True) / 100
        self.u_caida = p.num("U_caida_pct", "tensión de retorno en % de Uc", positivo=True) / 100
        if self.u_caida >= self.u_cierre:
            raise ModeloIncompleto(f"{p.quien}: la caída ({self.u_caida:.0%}) tiene que ser menor que la "
                                   f"conmutación ({self.u_cierre:.0%})")
        a = Parametros(p.designacion, p.ref, p.mapa("aire", "la ficha neumática de la válvula (la arma el "
                                                    "snapshot desde `neumatico:`)"))
        self.aire = a.modelo
        self.vias = int(a.num("vias", "número de vías", positivo=True))
        self.posiciones_n = int(a.num("posiciones", "número de posiciones", positivo=True))
        self.mando = a.texto("mando", "posición de reposo y retención", ("monoestable", "biestable", "centro_cerrado",
                                                                          "centro_escape", "centro_presion"))
        self.lados = a.lista("bobinas", "lados con bobina («14», «12»)")
        self.manual = a.booleano("manual", "si trae accionamiento manual")
        self.t_on = a.num("t_on_ms", "tiempo de conmutación al energizar", positivo=True) / 1000
        self.t_off = a.num("t_off_ms", "tiempo de conmutación al desenergizar", positivo=True) / 1000
        self.BOBINAS = ({self.lados[0]: "A1"} if len(self.lados) == 1
                        else {lado: f"{lado}A1" for lado in self.lados})
        self.FALLAS = {"pegada": "posicion?", "bobina_cortada": "canal" if len(self.lados) > 1 else ""}
        if self.posiciones_n == 3:
            self.posiciones = ("14", "0", "12")
            self.posicion = "0"
        elif self.vias == 5:
            self.posiciones = ("14", "12")
            self.posicion = "12"
        else:
            self.posiciones = ("12", "0")
            self.posicion = "0"
        if self.mando == "biestable":
            self.hipotesis.append("la biestable arranca en «12» (el cilindro retraído)")
        self.hipotesis.append(HIPOTESIS_CARRETE)
        self.energizada = {lado: False for lado in self.lados}
        self.manuales: set = set()
        self.cortadas: set = set()
        self.pegada: str | None = None
        self._hacia: str | None = None
        self._t = 0.0

    # ── el carrete ───────────────────────────────────────────────────────────────────────────

    def _activo(self, lado: str) -> bool:
        return self.energizada.get(lado, False) or lado in self.manuales

    def objetivo(self) -> str:
        activos = [lado for lado in self.lados if self._activo(lado)]
        if self.mando == "biestable" or (self.posiciones_n == 3 and len(activos) > 1):
            return activos[0] if len(activos) == 1 else self.posicion
        if self.posiciones_n == 3:
            return activos[0] if activos else "0"
        if self.vias == 5:
            return "14" if activos else "12"
        return "12" if activos else "0"

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        e = entradas or {}
        for lado in self.lados:
            u = 0.0 if lado in self.cortadas else magnitud(e.get(f"U_{lado}", 0.0))
            if u >= self.u_cierre * self.Uc - 1e-9:
                self.energizada[lado] = True
            elif u < self.u_caida * self.Uc:
                self.energizada[lado] = False
        if self.pegada is not None:
            self._hacia = None
            return self.salidas()
        obj = self.objetivo()
        if obj == self.posicion:
            self._hacia = None
        else:
            if obj != self._hacia:
                self._hacia, self._t = obj, 0.0
            self._t += dt
            t_req = self.t_on if (obj in self.lados and self._activo(obj)) else self.t_off
            if self._t >= t_req - EPS_T:
                self.posicion, self._hacia = obj, None
        return self.salidas()

    def abre_bobina(self, lado: str) -> bool:
        return lado in self.cortadas

    # ── acciones y fallas ────────────────────────────────────────────────────────────────────

    def _accion_accionar_manual(self, valor=None) -> None:
        if not self.manual:
            raise ValueError(f"{self.designacion} ({self.ref}): su ficha no trae accionamiento manual")
        v = str(valor) if valor is not None else ""
        if v == "0":
            self.manuales.clear()
        elif v in self.lados:
            self.manuales.add(v)
        else:
            raise ValueError(f"{self.designacion}: «accionar_manual» pide el lado ({', '.join(self.lados)}) "
                             "o «0» para soltarlo")

    def _falla_pegada(self, valor=None) -> str:
        pos = self.posicion if valor is None else str(valor)
        if pos not in self.posiciones:
            raise ValueError(f"{self.designacion}: «pegada» queda en una de sus posiciones "
                             f"({', '.join(self.posiciones)}), llegó {valor!r}")
        self.pegada = self.posicion = pos
        return f"pegada {pos}"

    def _reparar_pegada(self, _v=None):
        self.pegada = None
        return [e for e in (self._averias or {}) if e.startswith("pegada")]

    def _lado(self, valor) -> str:
        if valor is None and len(self.lados) == 1:
            return self.lados[0]
        if str(valor) not in self.lados:
            raise ValueError(f"{self.designacion}: «bobina_cortada» pide la bobina ({', '.join(self.lados)}), "
                             f"llegó {valor!r}")
        return str(valor)

    def _falla_bobina_cortada(self, valor=None) -> str:
        lado = self._lado(valor)
        self.cortadas.add(lado)
        return f"bobina_cortada {lado}"

    def _reparar_bobina_cortada(self, valor=None):
        lado = self._lado(valor)
        self.cortadas.discard(lado)
        return f"bobina_cortada {lado}"

    def salidas(self) -> dict:
        return {"posicion": self.posicion, **{f"bobina{lado}": self.energizada[lado] for lado in self.lados}}
