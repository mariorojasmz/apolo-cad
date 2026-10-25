"""El interruptor diferencial (RCCB, IEC 61008-1): dispara por la corriente RESIDUAL (plan
datos-de-corte-y-acometida, D8; F1b).

Lo que ve: I_Δ = |Σ fasores de sus polos|, con los caminos `proteccion` medidos de LÍNEA a CARGA
(el N incluido: en un aparato sano lo que sale por las fases vuelve por el N y la suma es cero;
lo que se va a tierra por una falla a PE no vuelve y es la residual). El tablero lo indexa aparte
de las protecciones térmicas y le pasa los FASORES (`I_fasores`, sin `abs`); un polo sin cablear
(el N de un 4P en una red sin neutro) no está en la red y no entra.

Disparo (IEC 61008-1, tipo general, bandas en `BANDAS_S`): no dispara a ½ IΔn; dispara a IΔn en
≤ 0,3 s, a 2 IΔn en ≤ 0,15 s y a 5 IΔn en ≤ 0,04 s. El umbral se fija en `K` × IΔn y el tiempo en
el medio de cada banda (criterio de diseño); la residual tiene que SOSTENERSE sobre el umbral
ese tiempo, y si baja el contador vuelve a cero (criterio de diseño). Determinista con Δt de
2 ms. No protege de sobrecorriente (es un RCCB): se compone con un ITM.

Hipótesis declaradas: A, B (y AC, F) dan lo mismo porque la red es fasorial y senoidal (la
componente continua lisa que ciega a un tipo A no se simula; el ERC lo señala, D10); la fuga
natural o capacitiva (filtros EMC, cables largos) no se simula: ve sólo las fallas declaradas.

Señales: `-F1.cerrado`, `-F1.disparado`, `-F1.I_residual_mA`, `-F1.causa` («diferencial»; con la
falla `abierto`, «avería») y, tras el primer disparo, `-F1.I_residual_disparo_mA`: la RESIDUAL
con que disparó (con `abierto`, la del último paso cerrado), retenida hasta rearmar y 0.0 después.
No publica `I_disparo_A`: dispara por la residual, no por la corriente de fase (plan
pedidos-de-extensiones D7, revisión de F4). Acciones: `rearmar`, `abrir`, `cerrar` (rearmar con la falla de
aislamiento presente vuelve a disparar en su tiempo de disparo: el aparato es de disparo libre).
Fallas (cosim-fallas D2): `no_dispara` (la residual se mide pero no abre) y `abierto` (dispara
solo; mientras dura no se rearma; reparada, queda disparado hasta que alguien lo rearme).
"""

from __future__ import annotations

from .base import EPS_T, Modelo, ModeloIncompleto, Parametros
from .protecciones import CorrienteDeDisparo

#: Clases de corriente residual de IEC 61008-1 / IEC 62423 (el YAML las valida como `curva`).
CLASES_RESIDUAL = ("AC", "A", "F", "B")
#: IEC 61008-1 (tipo general): no dispara a ½ IΔn y dispara a IΔn. Umbral en 0,75 × IΔn
#: (criterio de diseño: entre los dos).
NO_DISPARO, DISPARO = 0.5, 1.0
K = 0.75
#: IEC 61008-1, tiempo máximo de disparo (s) desde cada múltiplo de IΔn (tipo general).
BANDAS_S = ((1.0, 0.3), (2.0, 0.15), (5.0, 0.04))
#: Criterio de diseño: el tiempo de disparo en el medio de cada banda, sostenido sobre K.
T_DISPARO_S = ((5.0, 0.02), (2.0, 0.075), (K, 0.15))


#: Tolerancia relativa en el borde de una banda: 5 × IΔn armado con fasores puede llegar como
#: 4,999999… por el redondeo de la suma.
TOL_BORDE = 1e-9


def t_disparo(x: float) -> float | None:
    """Tiempo de disparo a x = I_Δ / IΔn (None: no dispara)."""
    for desde, t in T_DISPARO_S:
        if x >= desde * (1.0 - TOL_BORDE):
            return t
    return None


def residual(fasores) -> float:
    """|Σ fasores| en A (un escalar de la red de mando entra como fasor real)."""
    return abs(sum((complex(i) for i in fasores or ()), 0j))


class Diferencial(CorrienteDeDisparo, Modelo):
    tipo = "diferencial"
    SENAL = "I_residual_disparo_mA"
    ACCIONES = ("rearmar", "abrir", "cerrar")
    FALLAS = {"no_dispara": "", "abierto": ""}

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.In = p.num("In_A", "corriente asignada del diferencial", positivo=True)
        self.IDn = p.num("IDn_mA", "sensibilidad IΔn en mA, IEC 61008-1", positivo=True) / 1000.0
        self.clase = p.texto("clase_residual", "clase de corriente residual (IEC 61008-1)", CLASES_RESIDUAL)
        polos = p.num("polos", "polos del diferencial (2 o 4)")
        if polos not in (2, 4):
            raise ModeloIncompleto(f"{p.quien}: «polos» de un diferencial es 2 o 4, llegó {polos:g}")
        self.polos = int(polos)
        self.hipotesis.append(f"disparo a {K:g} × IΔn (IEC 61008-1: no dispara a ½ IΔn y dispara a IΔn; "
                              "el punto entre los dos es criterio de diseño)")
        self.hipotesis.append("tiempo de disparo en el medio de cada banda de IEC 61008-1: 0,15 s desde "
                              f"{K:g} IΔn, 0,075 s desde 2 IΔn y 0,02 s desde 5 IΔn (criterio de diseño)")
        self.hipotesis.append(f"clase {self.clase}: la red es fasorial y senoidal; la componente continua "
                              "lisa que ciega a un tipo A no se simula (A y B dan lo mismo)")
        self.hipotesis.append("la fuga natural o capacitiva (filtros EMC, cables largos) no se simula: "
                              "el diferencial ve sólo las fallas declaradas")
        self.manija = True
        self.disparado = False
        self.causa = ""
        self.no_dispara = False
        self.abierto = False
        self.I_res = 0.0
        self._t = 0.0

    @property
    def cerrado(self) -> bool:
        return self.manija and not self.disparado

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        self.I_res = residual((entradas or {}).get("I_fasores")) if self.cerrado else 0.0
        self._I_ultima = self.I_res * 1000.0  # mA, la unidad de `SENAL`
        t = t_disparo(self.I_res / self.IDn) if self.cerrado else None
        if t is None:
            self._t = 0.0
        else:
            self._t += dt
            if self._t >= t - EPS_T and not self.no_dispara:
                self.disparado, self.causa, self._t = True, "diferencial", 0.0
                self._retener(self._I_ultima)
        return self.salidas()

    def salidas(self) -> dict:
        return self._con_disparo({"cerrado": self.cerrado, "disparado": self.disparado,
                                  "I_residual_mA": round(self.I_res * 1000.0, 6), "causa": self.causa})

    # ── acciones y fallas ────────────────────────────────────────────────────────────────────

    def _accion_rearmar(self, _valor=None) -> None:
        if self.disparado and not self.abierto:
            self.disparado, self.causa, self._t = False, "", 0.0
            self._soltar()

    def _accion_abrir(self, _valor=None) -> None:
        self.manija = False

    def _accion_cerrar(self, _valor=None) -> None:
        self.manija = True

    def _falla_no_dispara(self, _v=None) -> None:
        self.no_dispara = True

    def _reparar_no_dispara(self, _v=None) -> None:
        self.no_dispara = False

    def _falla_abierto(self, _v=None) -> None:
        self.abierto = True
        if not self.disparado:
            self._retener(self._I_ultima)
        self.disparado, self.causa = True, "avería"

    def _reparar_abierto(self, _v=None) -> None:
        self.abierto = False
