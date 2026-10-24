"""Protecciones: ITM, guardamotor, relé térmico y fusible (plan V8.3 D1, D7).

Todas comparten la IMAGEN TÉRMICA de primer orden de un bimetal: con x = I/Ir,

    dθ/dt = (x² − θ)/τ        disparo cuando θ ≥ k²

(k = la corriente CONVENCIONAL de disparo / Ir, entre la de no disparo y la de disparo de su
norma). Desde frío dispara en t(x) = τ·ln(x²/(x² − k²)); por debajo de k no dispara nunca. El
paso es exacto (θ ← x² + (θ − x²)·e^(−dt/τ)): el resultado no depende del tamaño del paso más
que en su cuantización. τ se elige para que t(x) caiga en la banda de la norma (las bandas
están abajo, con su norma; el punto dentro de la banda es criterio de diseño), y el magnético
es un umbral instantáneo: dispara en el mismo paso.

Señales (D10): `-Q1.disparado`, `-Q1.termico_pct` (θ/k² en %), `-Q1.cerrado`.

Fallas (cosim-fallas D2): `no_dispara` (el bimetal calienta pero ni el térmico ni el magnético
abren) y `abierto` (dispara o funde SOLO, con causa «avería»: mientras dura no se rearma ni se
repone; reparada, queda disparada hasta que alguien la rearme, como un disparo de verdad).
"""

from __future__ import annotations

import math

from .base import Modelo, ModeloIncompleto, Parametros, decaimiento, por_polo

# ── bandas de norma ──────────────────────────────────────────────────────────────────────────

#: IEC 60947-4-1 (relés de sobrecarga): a 1,05 Ir no dispara en 2 h desde frío; a 1,2 Ir
#: dispara en < 2 h desde caliente. k = 1,125 (criterio de diseño: en medio de las dos).
RELE_NO_DISPARO, RELE_DISPARO = 1.05, 1.2
#: IEC 60947-4-1, tiempo de disparo Tp a 7,2 Ir desde frío por clase (s), y a 1,5 Ir desde
#: caliente (< 2 min en 10A/10, 4 min en 20, 8 min en 30).
BANDA_CLASE = {"10A": (2.0, 10.0), "10": (4.0, 10.0), "20": (6.0, 20.0), "30": (9.0, 30.0)}
LIMITE_1_5_CALIENTE_S = {"10A": 120.0, "10": 120.0, "20": 240.0, "30": 480.0}
#: Criterio de diseño: el Tp a 7,2 Ir se fija en el medio de la banda de la clase.
TP_7_2 = {c: (lo + hi) / 2 for c, (lo, hi) in BANDA_CLASE.items()}

#: IEC 60898-1 (ITM): a 1,13 In no dispara en 1 h desde frío; a 1,45 In dispara en < 1 h tras
#: 1,13; a 2,55 In desde frío dispara entre 1 y 60 s (In ≤ 32 A). Magnético instantáneo
#: (< 0,1 s) por curva, en × In: no dispara en el borde bajo y dispara en el alto.
ITM_NO_DISPARO, ITM_DISPARO = 1.13, 1.45
ITM_BANDA_2_55_S = (1.0, 60.0)
ITM_T_2_55_S = 10.0  # criterio de diseño: dentro de la banda 1–60 s
BANDA_MAGNETICA_ITM = {"B": (3.0, 5.0), "C": (5.0, 10.0), "D": (10.0, 20.0)}

#: IEC 60127-2 (cartuchos 5×20): no funde a 1,5 In en 1 h; a 2,75 / 4 / 10 In funde dentro de
#: estas bandas (s). F = rápido (hoja 1), T = temporizado (hoja 3).
BANDA_FUSIBLE = {
    "F": {2.75: (0.010, 2.0), 4.0: (0.003, 0.300), 10.0: (0.0, 0.020)},
    "T": {2.75: (0.200, 10.0), 4.0: (0.040, 3.0), 10.0: (0.010, 0.300)},
}
FUSIBLE_NO_FUNDE = 1.5
#: Criterio de diseño: k = 1,8 (entre 1,5 que no funde y 2,1 que funde) y τ que deja los tres
#: puntos de la hoja dentro de su banda.
FUSIBLE_K = 1.8
FUSIBLE_TAU_S = {"F": 0.3, "T": 3.0}


def _tau_para(t_s: float, x: float, k: float) -> float:
    """τ con el que una imagen térmica fría dispara en `t_s` a x = I/Ir."""
    return t_s / math.log(x * x / (x * x - k * k))


class ImagenTermica:
    """θ por polo (el bimetal de cada fase). Ver el docstring del módulo."""

    def __init__(self, tau_s: float, k: float, polos: int):
        self.tau, self.k2, self.polos = tau_s, k * k, polos
        self.theta = [0.0] * polos

    def paso(self, dt: float, x_por_polo: list[float]) -> bool:
        e = decaimiento(dt, self.tau)
        self.theta = [x * x + (th - x * x) * e for th, x in zip(self.theta, x_por_polo)]
        return max(self.theta) >= self.k2

    @property
    def pct(self) -> float:
        return 100.0 * max(self.theta) / self.k2

    def t_disparo(self, x: float, theta0: float = 0.0) -> float:
        """Tiempo analítico de disparo a x = I/Ir desde θ0 (inf si no dispara)."""
        if x * x <= self.k2:
            return math.inf
        if theta0 >= self.k2:
            return 0.0
        return self.tau * math.log((x * x - theta0) / (x * x - self.k2))


class _Proteccion(Modelo):
    """Estado común: cerrada (la manija), disparada (la protección abrió sola)."""

    ACCIONES = ("rearmar", "abrir", "cerrar")
    FALLAS = {"no_dispara": "", "abierto": ""}
    no_dispara = False
    abierto = False
    polos: int = 1
    nominal: float = 1.0  # la corriente a la que x = 1

    def _iniciar(self, termico: ImagenTermica, magnetico_A: float | None):
        self.termico = termico
        self.magnetico_A = magnetico_A
        self.manija = True
        self.disparado = False
        self.causa = ""

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        corrientes = por_polo((entradas or {}).get("I_A", 0.0), self.polos)
        if not self.cerrado:
            corrientes = [0.0] * self.polos
        termico = self.termico.paso(dt, [i / self.nominal for i in corrientes])
        if self.cerrado:
            if self.magnetico_A is not None and max(corrientes) >= self.magnetico_A:
                self._disparar("magnético")
            elif termico:
                self._disparar("térmico")
        return self.salidas()

    def _disparar(self, causa: str) -> None:
        if not self.no_dispara:
            self.disparado, self.causa = True, causa

    def _falla_no_dispara(self, _v=None) -> None:
        self.no_dispara = True

    def _reparar_no_dispara(self, _v=None) -> None:
        self.no_dispara = False

    def _falla_abierto(self, _v=None) -> None:
        self.abierto = True
        self.disparado, self.causa = True, "avería"

    def _reparar_abierto(self, _v=None) -> None:
        self.abierto = False

    @property
    def cerrado(self) -> bool:
        return self.manija and not self.disparado

    def salidas(self) -> dict:
        return {"cerrado": self.cerrado, "disparado": self.disparado,
                "termico_pct": round(self.termico.pct, 6), "causa": self.causa}

    def _puede_rearmar(self) -> bool:
        # el bimetal tiene que enfriarse hasta su régimen nominal (θ ≤ 1): criterio de diseño
        return max(self.termico.theta) <= 1.0 and not self.abierto

    def _accion_rearmar(self, _valor=None) -> None:
        if self.disparado and self._puede_rearmar():
            self.disparado, self.causa = False, ""

    def _accion_abrir(self, _valor=None) -> None:
        self.manija = False

    def _accion_cerrar(self, _valor=None) -> None:
        self.manija = True


def _polos(texto) -> int:
    """Polos PROTEGIDOS: «1P+N» protege uno (el neutro sólo se maniobra)."""
    if isinstance(texto, str) and "+N" in texto.upper():
        return 1
    return max(1, int(texto))


class Itm(_Proteccion):
    """ITM curva B/C/D (IEC 60898-1). Los polos disparan juntos (el aparato es uno)."""

    tipo = "itm"

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.nominal = p.num("In_A", "corriente asignada del ITM", positivo=True)
        self.curva = p.texto("curva", "curva de disparo IEC 60898-1", tuple(BANDA_MAGNETICA_ITM))
        self.polos = _polos(p.modelo.get("polos", 1))
        lo, hi = BANDA_MAGNETICA_ITM[self.curva]
        self.Im_In = (lo + hi) / 2
        p.hipotesis.append(f"magnético a {self.Im_In:g} × In: medio de la banda {lo:g}–{hi:g} "
                           f"de la curva {self.curva} (IEC 60898-1; criterio de diseño)")
        k = (ITM_NO_DISPARO + ITM_DISPARO) / 2
        self._iniciar(ImagenTermica(_tau_para(ITM_T_2_55_S, 2.55, k), k, self.polos),
                      self.Im_In * self.nominal)


class Guardamotor(_Proteccion):
    """Guardamotor: térmico de clase (IEC 60947-4-1) con Ir AJUSTADO + magnético FIJO en
    `Ii_A` (13 × Ir máx del aparato: no sigue al dial)."""

    tipo = "guardamotor"
    polos = 3

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.nominal = p.ajustado("Ir_A", "corriente de reglaje del térmico (el dial)")
        self.clase = p.texto("clase", "clase de disparo IEC 60947-4-1", tuple(BANDA_CLASE))
        k = (RELE_NO_DISPARO + RELE_DISPARO) / 2
        self._iniciar(ImagenTermica(_tau_para(TP_7_2[self.clase], 7.2, k), k, self.polos),
                      p.num("Ii_A", "disparo magnético fijo del guardamotor", positivo=True))


class ReleTermico(_Proteccion):
    """Relé térmico de sobrecarga (IEC 60947-4-1), sin magnético. Su «disparo» abre el 95-96 y
    cierra el 97-98; no corta la potencia él mismo (lo hace el contactor que comanda)."""

    tipo = "rele_termico"
    polos = 3
    ACCIONES = ("rearmar",)

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.nominal = p.ajustado("Ir_A", "corriente de reglaje del relé (el dial)")
        self.clase = p.texto("clase", "clase de disparo IEC 60947-4-1", tuple(BANDA_CLASE))
        self.rearme = p.texto("rearme", "rearme del relé", ("manual", "automatico"))
        k = (RELE_NO_DISPARO + RELE_DISPARO) / 2
        self._iniciar(ImagenTermica(_tau_para(TP_7_2[self.clase], 7.2, k), k, self.polos), None)

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        corrientes = por_polo((entradas or {}).get("I_A", 0.0), self.polos)
        if self.termico.paso(dt, [i / self.nominal for i in corrientes]) and not self.disparado:
            self._disparar("térmico")
        if self.disparado and self.rearme == "automatico" and self._puede_rearmar():
            self.disparado, self.causa = False, ""
        return self.salidas()


class Fusible(Modelo):
    """Cartucho 5×20 (IEC 60127-2) en cada unidad de un portafusible (bornera de `cantidad`
    unidades, cada una con su cartucho). Fundido queda fundido: se repone con `reponer`."""

    tipo = "fusible"
    ACCIONES = ("reponer",)
    FALLAS = {"no_dispara": "", "abierto": "unidad?"}
    no_dispara = False

    def __init__(self, p: Parametros, cantidad: int = 1):
        super().__init__(p)
        self.nominal = p.ajustado("cartucho_In_A", "corriente asignada del cartucho 5×20")
        maximo = p.num("In_max_A", "máximo que admite el portafusible", positivo=True)
        if self.nominal > maximo + 1e-12:
            raise ModeloIncompleto(f"{p.quien}: un cartucho de {self.nominal:g} A no entra en un "
                                   f"portafusible de {maximo:g} A")
        self.curva = p.texto("cartucho_curva", "curva del cartucho (F rápido, T temporizado)",
                             tuple(FUSIBLE_TAU_S))
        self.unidades = int(cantidad)
        self.termico = ImagenTermica(FUSIBLE_TAU_S[self.curva], FUSIBLE_K, self.unidades)
        self.fundido = [False] * self.unidades
        self.abiertas: set[int] = set()  # unidades con la falla `abierto` (0-indexadas)

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        corrientes = por_polo((entradas or {}).get("I_A", 0.0), self.unidades)
        corrientes = [0.0 if f else i for f, i in zip(self.fundido, corrientes)]
        self.termico.paso(dt, [i / self.nominal for i in corrientes])
        if not self.no_dispara:
            self.fundido = [f or th >= self.termico.k2 for f, th in zip(self.fundido, self.termico.theta)]
        return self.salidas()

    def salidas(self) -> dict:
        out = {"disparado": any(self.fundido), "termico_pct": round(self.termico.pct, 6)}
        if self.unidades > 1:
            out.update({f"{k + 1}.disparado": f for k, f in enumerate(self.fundido)})
        return out

    def _accion_reponer(self, unidad=None) -> None:
        for k in range(self.unidades):
            if unidad in (None, k + 1) and k not in self.abiertas:
                self.fundido[k] = False
                self.termico.theta[k] = 0.0

    def _unidades(self, unidad) -> list[int]:
        if unidad is None:
            return list(range(self.unidades))
        if isinstance(unidad, bool) or not isinstance(unidad, int) or not 1 <= unidad <= self.unidades:
            raise ValueError(f"{self.designacion}: la unidad va de 1 a {self.unidades} (llegó {unidad!r})")
        return [unidad - 1]

    def _etiqueta(self, unidad) -> str:
        return "abierto" if unidad is None or self.unidades == 1 else f"abierto {unidad}"

    def _falla_no_dispara(self, _v=None) -> None:
        self.no_dispara = True

    def _reparar_no_dispara(self, _v=None) -> None:
        self.no_dispara = False

    def _falla_abierto(self, unidad=None) -> str:
        for k in self._unidades(unidad):
            self.abiertas.add(k)
            self.fundido[k] = True
        return self._etiqueta(unidad)

    def _reparar_abierto(self, unidad=None) -> list[str]:
        ks = self._unidades(unidad)
        self.abiertas.difference_update(ks)
        if unidad is None:
            return [e for e, n in (self._averias or {}).items() if n == "abierto"]
        return [self._etiqueta(unidad)]
