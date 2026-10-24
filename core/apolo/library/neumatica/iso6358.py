"""Caudal de un componente neumático por ISO 6358-1:2013 y las conversiones de ENTRADA (plan V8.9 D3).

El modelo de caudal es UNO: la conductancia sónica `C` y la relación de presión crítica `b` de
ISO 6358-1:2013 (§ 3 y anexo A, ecuación del caudal másico):

    q_m = C · ρ0 · p1 · √(T0/T1) · φ,   φ = 1                                si p2/p1 ≤ b (sónico)
                                         φ = [1 − ((p2/p1 − b)/(1 − b))²]^m   si b < p2/p1 ≤ 1

con el aire de referencia ANR de ISO 8778:2003 (T0 = 293,15 K, p_ANR = 100 kPa, ρ0 = 1,185 kg/m³).
`m` es el índice subsónico de la 2013; cuando la ficha no lo trae se toma m = 0,5, la forma
elíptica de ISO 6358:1989, y se DECLARA como hipótesis. La presión de apertura Δpc de la 2013 no
se modela (Δpc = 0, válido para válvulas y orificios; no para una válvula antirretorno).

Kv, Cv, Qn y el área efectiva S son coeficientes de OTRA definición: entran sólo como dato de
ficha y se convierten a C evaluando la fórmula de arriba en el punto de medición que la ficha
declara, con el `b` de la ficha o declarado como hipótesis (nunca un `b` silencioso).

Unidades: presiones en bar ABSOLUTOS salvo que el nombre diga `_g` (manométricos); C en
dm³/(s·bar); caudales volumétricos en dm³/s (= L/s) ANR salvo que el nombre diga otra cosa.
"""

from __future__ import annotations

import math

#: Aire de referencia ANR (ISO 8778:2003): 20 °C, 100 kPa, 65 % de humedad relativa.
T_ANR_K = 293.15
P_ANR_BAR = 1.0
RHO_ANR_KG_M3 = 1.185

#: Estado normal de DIN 1343 (0 °C, 101,325 kPa): la referencia de los «Nm³» de las fórmulas de
#: Kv para gases (VDI/VDE 2173) y de algunos caudales nominales. Densidad del aire seco en ese
#: estado: 1,293 kg/m³ (DIN 1343).
T_DIN1343_K = 273.15
P_DIN1343_BAR = 1.01325
RHO_DIN1343_KG_M3 = 1.293

#: Atmósfera estándar a nivel del mar (ISO 2533): la presión ambiente que se SUPONE cuando el
#: proyecto no declara la de su sitio; quien la usa la lista como hipótesis.
P_ATM_ESTANDAR_BAR = 1.01325

#: Índice subsónico cuando la ficha no lo trae (forma elíptica de ISO 6358:1989).
M_SUBSONICO_ELIPTICO = 0.5

#: Aire como gas ideal: k = cp/cv = 1,4 y R = 287,05 J/(kg·K) (aire seco).
K_AIRE = 1.4
R_AIRE = 287.05

#: Referencias admitidas para un caudal nominal de ficha.
REFERENCIAS_QN = ("ANR", "DIN1343")


def phi(r: float, b: float, m: float = M_SUBSONICO_ELIPTICO) -> float:
    """Factor de caudal de ISO 6358-1:2013 para la relación r = p2/p1 (0 ≤ r ≤ 1)."""
    if not 0.0 <= b < 1.0:
        raise ValueError(f"b va en [0, 1): llegó {b}")
    if r <= b:
        return 1.0
    if r >= 1.0:
        return 0.0
    return (1.0 - ((r - b) / (1.0 - b)) ** 2) ** m


def caudal_anr(C: float, b: float, p1: float, p2: float, *, T1_K: float = T_ANR_K,
               m: float = M_SUBSONICO_ELIPTICO) -> float:
    """Caudal volumétrico ANR (dm³/s) de p1 a p2 (bar absolutos), ≥ 0; 0 si p1 ≤ p2.

    Es q_m / ρ0: el caudal másico de ISO 6358-1 expresado como volumen de aire ANR."""
    if p1 <= p2:
        return 0.0
    return C * p1 * math.sqrt(T_ANR_K / T1_K) * phi(p2 / p1, b, m)


def caudal_masico(C: float, b: float, p1: float, p2: float, *, T1_K: float = T_ANR_K,
                  m: float = M_SUBSONICO_ELIPTICO) -> float:
    """Caudal másico (kg/s) de ISO 6358-1:2013 de p1 a p2 (bar absolutos)."""
    return caudal_anr(C, b, p1, p2, T1_K=T1_K, m=m) * 1e-3 * RHO_ANR_KG_M3


def c_serie(*Cs: float) -> float:
    """C equivalente de componentes en serie por 1/C² = Σ 1/Cᵢ².

    Es una APROXIMACIÓN (la del prototipo de la F0, exacta sólo si todos trabajan sónicos con el
    mismo b): ISO 6358-3 trae el método de la norma. Quien la usa la declara como hipótesis."""
    if not Cs or any(c <= 0 for c in Cs):
        raise ValueError(f"cada C debe ser > 0: {Cs}")
    return 1.0 / math.sqrt(sum(1.0 / c ** 2 for c in Cs))


def _a_anr(q_l_min: float, referencia: str) -> float:
    """Un caudal nominal en L/min de su referencia → dm³/s ANR (gas ideal: q·(T_ANR/T)·(p/p_ANR))."""
    if referencia == "ANR":
        return q_l_min / 60.0
    if referencia == "DIN1343":
        return q_l_min / 60.0 * (T_ANR_K / T_DIN1343_K) * (P_DIN1343_BAR / P_ANR_BAR)
    raise ValueError(f"referencia «{referencia}»: opciones {', '.join(REFERENCIAS_QN)}")


def c_desde_qn(qn_l_min: float, p1_g: float, p2_g: float, b: float, *, referencia: str,
               p_atm: float = P_ATM_ESTANDAR_BAR, m: float = M_SUBSONICO_ELIPTICO) -> float:
    """C a partir de un caudal nominal medido de p1_g a p2_g (bar manométricos; el usual de
    catálogo es de 6 a 5 bar), en L/min de su `referencia` (ANR o DIN1343), con el `b` dado:
    C = q_ANR / (p1 · φ(p2/p1, b)), la fórmula de ISO 6358-1 despejada en el punto de medición."""
    p1, p2 = p1_g + p_atm, p2_g + p_atm
    if not p1 > p2:
        raise ValueError(f"el punto de medición necesita p1 > p2 (llegó {p1_g} → {p2_g} bar)")
    return _a_anr(qn_l_min, referencia) / (p1 * phi(p2 / p1, b, m))


def c_desde_s(S_mm2: float) -> float:
    """C de un área efectiva S (mm²) tratada como tobera IDEAL en bloqueo sónico (k = 1,4):
    q_m = S · p1 · √(k/(R·T0)) · (2/(k+1))^((k+1)/(2(k−1))) y C = q_m/(ρ0·p1). Da C ≈ 0,199·S,
    el orden de la regla de catálogo S ≈ 5·C (SMC, datos técnicos de caudal; a confirmar). Su
    `b` natural sería 0,528; la ficha declara el suyo."""
    psi = math.sqrt(K_AIRE / (R_AIRE * T_ANR_K)) * (2.0 / (K_AIRE + 1.0)) ** (
        (K_AIRE + 1.0) / (2.0 * (K_AIRE - 1.0)))
    return S_mm2 * 1e-6 * psi / RHO_ANR_KG_M3 * 1e3 * 1e5


#: Cv → Kv por las definiciones de unidades (galón US = 3,785411784 L a 60 °F; psi = 0,0689475729
#: bar): Kv = Cv · 0,2271247 / √0,0689476 = 0,86497·Cv. IEC 60534-1 lo redondea a 0,865.
KV_POR_CV = (3.785411784e-3 * 60.0) / math.sqrt(0.0689475729)


def kv_desde_cv(cv: float) -> float:
    return cv * KV_POR_CV


def qn_desde_kv(kv: float, p1_g: float, p2_g: float, *, p_atm: float = P_ATM_ESTANDAR_BAR,
                T1_K: float = T_ANR_K) -> float:
    """Caudal de aire (L/min, estado normal DIN 1343) por un Kv, con la fórmula de gases de
    VDI/VDE 2173 (constantes 514 y 257 transcritas de la literatura de válvulas de proceso; a
    confirmar contra la norma): subcrítico (Δp < p1/2) Q = 514·Kv·√(Δp·p2/(ρN·T1)); crítico
    Q = 257·Kv·p1/√(ρN·T1), con Q en m³/h, p en bar absolutos y T1 en K."""
    p1, p2 = p1_g + p_atm, p2_g + p_atm
    if not p1 > p2:
        raise ValueError(f"el punto de medición necesita p1 > p2 (llegó {p1_g} → {p2_g} bar)")
    dp = p1 - p2
    if dp < p1 / 2.0:
        q_m3_h = 514.0 * kv * math.sqrt(dp * p2 / (RHO_DIN1343_KG_M3 * T1_K))
    else:
        q_m3_h = 257.0 * kv * p1 / math.sqrt(RHO_DIN1343_KG_M3 * T1_K)
    return q_m3_h * 1000.0 / 60.0


def c_desde_kv(kv: float, p1_g: float, p2_g: float, b: float, *, p_atm: float = P_ATM_ESTANDAR_BAR,
               m: float = M_SUBSONICO_ELIPTICO) -> float:
    """C de un Kv: el caudal de VDI/VDE 2173 en el punto de medición, despejado con ISO 6358-1."""
    qn = qn_desde_kv(kv, p1_g, p2_g, p_atm=p_atm)
    return c_desde_qn(qn, p1_g, p2_g, b, referencia="DIN1343", p_atm=p_atm, m=m)


def c_desde_cv(cv: float, p1_g: float, p2_g: float, b: float, *, p_atm: float = P_ATM_ESTANDAR_BAR,
               m: float = M_SUBSONICO_ELIPTICO) -> float:
    return c_desde_kv(kv_desde_cv(cv), p1_g, p2_g, b, p_atm=p_atm, m=m)


def velocidad_regimen_sonica(C_escape: float, A_escape_mm2: float) -> float:
    """Velocidad (m/s) de un pistón cuyo ESCAPE trabaja en bloqueo sónico (plan V8.9 D10).

    En bloqueo el caudal ANR es C·p_cámara y el volumen que deja la cámara, a su presión, es
    C·p_ANR por segundo (isoterma a T0): v = C·p_ANR / A_escape, independiente de la presión de la
    cámara. Vale mientras p_atm / p_cámara ≤ b (lo comprueba quien la usa: `calculo.regimen`)."""
    if A_escape_mm2 <= 0:
        raise ValueError(f"área de escape > 0: {A_escape_mm2}")
    return C_escape * P_ANR_BAR * 1e-3 / (A_escape_mm2 * 1e-6)
