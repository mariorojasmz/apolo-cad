"""Motor de inducción + reductor como fuente de par para la dinámica (V8.2 D3).

La curva par–deslizamiento de un motor de inducción sigue la fórmula de Kloss:

    T(s) = 2·Tk / (s/sk + sk/s)

con Tk el par máximo (de vuelco) y sk su deslizamiento. Cerca del sincronismo (s ≪ sk) la
curva es casi una recta, T ≈ 2·Tk·s/sk: la RAMA ESTABLE. Reflejada a la salida de un reductor
de relación i y rendimiento η, esa recta es un amortiguador viscoso contra la velocidad
síncrona:

    T_salida = kv·(ωs/i − ω_salida),   kv = 2·Tk/(sk·ωs)·i²·η,   |T_salida| ≤ Tk·i·η

que es EXACTAMENTE el actuador `<velocity>` de MuJoCo (`kv`, `forcerange`). V8.0 midió que
integrarlo nativo queda exacto con cualquier intercambio, mientras que el par de Kloss
calculado en Python oscila desde un intercambio de 4 ms (plan V8, § Bitácora V8.0).

Con variador en V/f constante (f ≤ f nominal) el par máximo y la VELOCIDAD de deslizamiento
(sk·ωs) se mantienen, así que `kv` no cambia con la frecuencia: sólo la consigna ωs(f)/i. Por
encima de la nominal (debilitamiento de campo) el par máximo cae con (fn/f)².

Puro: recibe los datos de placa como dict, nunca un `Document`. Unidades SI (N·m, rad/s).
"""

from __future__ import annotations

import math

#: Par máximo / nominal cuando la placa no lo trae. IEC 60034-1 exige ≥ 1,6; los motores
#: IE2/IE3 de 4 polos y baja potencia rondan 2,3–3. Criterio de diseño: verificar con la placa.
TK_TN_DEFECTO = 2.5

#: Frecuencia de red por defecto (perfil Perú, V8 D11).
FRECUENCIA_DEFECTO_HZ = 60.0

_CLAVES = {"potencia_kW", "rpm", "frecuencia_hz", "polos", "tk_tn", "inercia_rotor_kgm2"}


def inercia_rotor_estimada(potencia_kw: float) -> float:
    """kg·m² del rotor de un motor TEFC de 4 polos: J ≈ 0,0033·P^1,16 (ajuste al orden de
    magnitud de catálogos IEC de 0,75 a 7,5 kW). Criterio de diseño: la placa manda.

    No es un detalle: reflejada por el reductor (J·i²) DOMINA la inercia de una faja (con
    i = 40, 0,005 kg·m² del rotor pesan 8 kg·m² en el tambor, contra 0,07 del tambor) y sin
    ella el arranque directo a par máximo salta en un paso de 1 ms más allá de la consigna."""
    return 0.0033 * max(float(potencia_kw), 0.0) ** 1.16


def _num(placa: dict, clave: str, *, positivo: bool = True) -> float:
    try:
        valor = float(placa[clave])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"datos de placa: '{clave}' debe ser un número") from exc
    if positivo and not valor > 0:
        raise ValueError(f"datos de placa: '{clave}' debe ser > 0 (vino {valor:g})")
    return valor


def kloss_par(s: float, tk: float, sk: float) -> float:
    """Par de Kloss (N·m, lado motor) para un deslizamiento `s`."""
    if abs(s) < 1e-12:
        return 0.0
    return 2.0 * tk / (s / sk + sk / s)


def kloss_linealizado(
    datos_placa: dict,
    i: float = 1.0,
    eta: float = 1.0,
    frecuencia_hz: float | None = None,
) -> dict:
    """Rama estable de Kloss reflejada a la salida del reductor.

    `datos_placa`: `potencia_kW` y `rpm` (velocidad NOMINAL del motor) obligatorios;
    `frecuencia_hz` (nominal, 60 por defecto), `polos` (si falta, se deduce de rpm y f),
    `tk_tn` (par máximo/nominal, 2,5 por defecto) e `inercia_rotor_kgm2` (estimada por
    potencia si falta): los defaults son criterio de diseño y se declaran. `i` es la relación
    del reductor (ω_motor/ω_salida) y `eta` su rendimiento. `frecuencia_hz` es la que entrega
    el variador (por defecto, la nominal).

    Devuelve, a la SALIDA: `kv` (N·m·s/rad), `par_max_Nm` (= Tk·i·η, el `forcerange`),
    `omega_sinc_rad_s` (= ωs(f)/i, la consigna), `omega_nominal_rad_s` (= ωs(1−sn)/i, con la
    frecuencia nominal) e `inercia_reflejada_kgm2` (= J_rotor·i²); y del motor: `Tn_Nm`,
    `Tk_Nm`, `sn`, `sk`, `polos`, `ns_rpm`, `inercia_rotor_kgm2`, más las `hipotesis`."""
    if not isinstance(datos_placa, dict):
        raise ValueError("datos de placa: se espera un objeto {potencia_kW, rpm, …}")
    sobran = set(datos_placa) - _CLAVES
    if sobran:
        raise ValueError(
            f"datos de placa: clave(s) desconocida(s) {sorted(sobran)}; "
            f"las válidas son {sorted(_CLAVES)}"
        )
    for clave in ("potencia_kW", "rpm"):
        if clave not in datos_placa:
            raise ValueError(f"datos de placa: falta '{clave}'")
    hipotesis: list[str] = []
    pn_w = _num(datos_placa, "potencia_kW") * 1000.0
    nn = _num(datos_placa, "rpm")
    fn = (_num(datos_placa, "frecuencia_hz") if "frecuencia_hz" in datos_placa
          else FRECUENCIA_DEFECTO_HZ)
    if "frecuencia_hz" not in datos_placa:
        hipotesis.append(f"frecuencia nominal {fn:g} Hz (perfil Perú)")
    if "polos" in datos_placa:
        polos = int(round(_num(datos_placa, "polos")))
        if polos < 2 or polos % 2:
            raise ValueError(f"datos de placa: 'polos' debe ser par y ≥ 2 (vino {polos})")
    else:
        polos = max(2, 2 * int(round(60.0 * fn / nn)))
        hipotesis.append(f"{polos} polos deducidos de {nn:g} rpm a {fn:g} Hz")
    ns = 120.0 * fn / polos
    sn = (ns - nn) / ns
    if not 0.0 < sn < 0.5:
        raise ValueError(
            f"datos de placa: {nn:g} rpm no es coherente con {polos} polos a {fn:g} Hz "
            f"(síncrona {ns:g} rpm, deslizamiento {sn:.3f}); revisa 'rpm' o 'polos'"
        )
    if "tk_tn" in datos_placa:
        lam = _num(datos_placa, "tk_tn")
    else:
        lam = TK_TN_DEFECTO
        hipotesis.append(f"Tk/Tn = {lam:g} (criterio de diseño; verificar con la placa)")
    if lam <= 1.0:
        raise ValueError(f"datos de placa: 'tk_tn' debe ser > 1 (vino {lam:g})")
    if "inercia_rotor_kgm2" in datos_placa:
        j_rotor = _num(datos_placa, "inercia_rotor_kgm2")
    else:
        j_rotor = inercia_rotor_estimada(pn_w / 1000.0)
        hipotesis.append(f"inercia del rotor {j_rotor:.4f} kg·m² estimada por potencia "
                         "(criterio de diseño; verificar con la placa)")
    if not i > 0:
        raise ValueError(f"la relación del reductor debe ser > 0 (vino {i:g})")
    if not 0.0 < eta <= 1.0:
        raise ValueError(f"el rendimiento del reductor debe estar en (0, 1] (vino {eta:g})")

    omega_n = 2.0 * math.pi * nn / 60.0
    tn = pn_w / omega_n
    tk = lam * tn
    sk = sn * (lam + math.sqrt(lam * lam - 1.0))
    ws_nominal = 2.0 * math.pi * ns / 60.0
    f = fn if frecuencia_hz is None else float(frecuencia_hz)
    if f < 0:
        raise ValueError(f"la frecuencia del variador debe ser ≥ 0 (vino {f:g})")
    ws_f = ws_nominal * f / fn
    tk_f = tk
    if f > fn:
        tk_f = tk * (fn / f) ** 2
        hipotesis.append(f"{f:g} Hz > {fn:g} Hz: debilitamiento de campo, Tk·(fn/f)²")
    kv = 2.0 * tk / (sk * ws_nominal) * i * i * eta
    return {
        "kv": kv,
        "par_max_Nm": tk_f * i * eta,
        "omega_sinc_rad_s": ws_f / i,
        "omega_nominal_rad_s": ws_nominal * (1.0 - sn) / i,
        "inercia_reflejada_kgm2": j_rotor * i * i,
        "inercia_rotor_kgm2": j_rotor,
        "Tn_Nm": tn,
        "Tk_Nm": tk,
        "sn": sn,
        "sk": sk,
        "polos": polos,
        "ns_rpm": ns,
        "frecuencia_hz": f,
        "hipotesis": hipotesis,
    }
