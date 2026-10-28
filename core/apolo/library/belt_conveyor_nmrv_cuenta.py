"""La cuenta del motorreductor SINFÍN de eje hueco de `create_belt_conveyor` (plan faja-compacta,
D2). Pura: de las cotas a los números, sin OCCT. La geometría, en `belt_conveyor_nmrv.py`.

- **Calce**: el eje hueco del NMRV (`bore_d` de ficha, H8, chavetero de ficha) se calza en el
  extremo del eje motriz: su Ø tiene que ser el del eje del tambor (`eje_mm`); si no, error que
  nombra los NMRV que calzan. La plantilla no elige el tamaño: lo pide el modelador y la cuenta lo
  juzga (los demás motores, igual).
- **Relación**: la de la serie de catálogo (`specs.relaciones_i`) cuya velocidad de banda queda
  más cerca de la `velocidad` pedida, con la velocidad del motor de su placa (`n_rpm`) y el Ø
  EXTERIOR del tambor motriz (engomado incluido: lo que abraza la banda).
- **Potencia** (el método de `rules_faja_motor`: CEMA slider-bed, P = F·v/η·margen): F = g·μ·(carga
  + banda) con μ = 0,33 (banda sobre cama), la carga de diseño de la cama (`CARGA_KG_M`, la misma de
  `belt_conveyor_cama.py`: la plantilla no recibe la del encargo) y el peso del lazo de banda (PVC);
  η = 0,75 del sinfín-corona (`rules_enriquecer`, ya reconocida por la regla) y el margen de servicio
  `POWER_MARGIN`. Si la placa del motor no alcanza: error con el NMRV siguiente que alcanza.
- **Brazo de reacción**: con el par de ARRANQUE (2 × el nominal de salida: arranque directo de un
  motor de inducción, el criterio de la base del coaxial, `belt_conveyor_motor.ARRANQUE`), la fuerza
  en el anclaje F = T / R; la flexión del brazo en su raíz (σ ≤ 0,6·f_y, A36), el corte del perno del
  anclaje (EN 1993-1-8 tabla 3.4) y el cordón del soporte a la pata (anillo de Ø`D_SOPORTE` como
  línea, τ ≤ 0,30·F_EXX: AISC 360 J2.4, el de la base del coaxial).
"""

from __future__ import annotations

import math

from .catalog import CATALOG, refs_in_category

ETA_SINFIN = 0.75        # sinfín-corona (rules_enriquecer: el η que la regla ya reconoce)
CATEGORIA = "motorreductores_sinfin"
FY_A36 = 250.0           # MPa, la chapa del brazo
D_SOPORTE = 40.0         # Ø de la barra del soporte del anclaje (belt_conveyor_nmrv.py)
GARGANTA_SOPORTE = 4.0
PERNO_ANCLAJE = "M12"


def es_sinfin(ref: str | None) -> bool:
    return bool(ref) and ref in CATALOG and CATALOG[ref].category == CATEGORIA


def calzan(d: float) -> list[str]:
    """Los motorreductores sinfín cuyo eje hueco calza en un eje de Ø `d`."""
    return [r for r in refs_in_category(CATEGORIA)
            if math.isclose(float(CATALOG[r].params["bore_d"]), d)]


def calce(ref: str, d: float, tambor: str) -> None:
    bore = float(CATALOG[ref].params["bore_d"])
    if not math.isclose(bore, d):
        ok = calzan(d)
        raise ValueError(f"el eje hueco del {ref} (Ø{bore:g}) no calza en el eje Ø{d:g} del "
                         f"{tambor}: " + (f"calzan {', '.join(ok)}" if ok else
                                          "ningún motorreductor sinfín de catálogo calza"))


def _potencia_kw(ref: str) -> float:
    return float(CATALOG[ref].specs["potencia_kW"])


def cuenta(c, largo_lazo: float) -> dict:
    """La cuenta del NMRV de la faja `c` (para `Plan.calculos["motorreductor"]`). ValueError si no
    calza, si falta la velocidad o si la potencia no alcanza."""
    from .belt_conveyor_cama import CARGA_KG_M
    from .engineering.belt import BED_FRICTION, belt_power_kw, belt_pull_n
    from .materials import density
    from .rules_comun import POWER_MARGIN

    ref = c.motor
    calce(ref, c.d_m, c.tambor_m)
    if not c.velocidad or c.velocidad <= 0:
        raise ValueError(f"el {ref} es un motorreductor sinfín: pide la `velocidad` de la banda "
                         "(m/s) para elegir su relación")
    comp = CATALOG[ref]
    n_motor = float(comp.electrico.modelo["n_rpm"])
    d_ext = 2.0 * c.r_m
    n_pedida = c.velocidad * 60.0 / (math.pi * d_ext / 1000.0)
    serie = [float(i) for i in comp.specs["relaciones_i"]]
    i = min(serie, key=lambda k: abs(n_motor / k - n_pedida))
    n_tambor = n_motor / i
    v = n_tambor * math.pi * d_ext / 1000.0 / 60.0
    carga = CARGA_KG_M * c.largo / 1000.0
    banda = density("pvc") * c.t * c.ancho * largo_lazo
    f = belt_pull_n(carga, banda)
    p_req = belt_power_kw(f, v, ETA_SINFIN, POWER_MARGIN)
    p = _potencia_kw(ref)
    out = {
        "titulo": "Motorreductor sinfín de eje hueco",
        "entradas": {"motorreductor": ref, "velocidad pedida": f"{c.velocidad:g} m/s",
                     "motor": f"{n_motor:g} rpm", "Ø tambor (engomado)": f"{d_ext:.1f} mm",
                     "carga de diseño": f"{CARGA_KG_M:g} kg/m × {c.largo / 1000.0:g} m",
                     "banda": f"{banda:.1f} kg", "μ banda-cama": f"{BED_FRICTION}",
                     "η sinfín": f"{ETA_SINFIN}", "margen": f"{POWER_MARGIN}x"},
        "formula": "i: la de la serie más cerca de n_motor·π·D/(60·v); P = F·v/η·margen, "
                   "F = g·μ·(carga + banda)",
        "sustitucion": (f"i = {i:g} → {n_tambor:.1f} rpm → v = {v:.3f} m/s; F = 9,81·{BED_FRICTION}"
                        f"·({carga:.0f} + {banda:.1f}) = {f:.0f} N; P = {f:.0f}·{v:.3f}/"
                        f"{ETA_SINFIN}·{POWER_MARGIN}"),
        "resultado": f"P requerida = {p_req:.2f} kW; motor {p:g} kW",
        "criterio": "P motor ≥ P requerida",
        "fs": round(p / p_req, 2) if p_req > 0 else None,
        "norma": "CEMA (unit handling) — slider bed; carga: criterio de diseño (la de la cama)",
        "relacion": i, "n_tambor_rpm": round(n_tambor, 1), "v_m_s": round(v, 3),
        "p_req_kw": round(p_req, 3), "p_motor_kw": p,
        "par_salida_nm": round(p * 1000.0 * ETA_SINFIN / (n_tambor * 2.0 * math.pi / 60.0), 1),
    }
    if p < p_req:
        mas = sorted((r for r in refs_in_category(CATEGORIA) if _potencia_kw(r) >= p_req),
                     key=_potencia_kw)
        sig = next((r for r in mas if r in calzan(c.d_m)), None)
        que = (f"usa el {sig} ({_potencia_kw(sig):g} kW)" if sig else
               (f"el {mas[0]} ({_potencia_kw(mas[0]):g} kW) alcanza pero su eje hueco Ø"
                f"{CATALOG[mas[0]].params['bore_d']:g} no calza en el eje Ø{c.d_m:g}: usa un tambor "
                f"de ese eje o baja la velocidad" if mas else "baja la velocidad"))
        raise ValueError(f"el {ref} ({p:g} kW) no alcanza: la banda a {v:.2f} m/s pide "
                         f"{p_req:.2f} kW (CEMA slider-bed, η {ETA_SINFIN} del sinfín, "
                         f"{CARGA_KG_M:g} kg/m de diseño): {que}")
    out["ok"] = True
    return out


def cuenta_brazo(par_salida_nm: float, r_mm: float, ancho_mm: float, t_mm: float,
                 raiz_mm: float, voladizo_mm: float) -> dict:
    """El brazo de reacción con el par de arranque: `r_mm` = del eje al anclaje, `raiz_mm` = del
    anclaje a la raíz del brazo (donde empieza el disco), `voladizo_mm` = del cordón del soporte al
    plano del brazo (el brazo de palanca de la fuerza sobre la soldadura)."""
    from .belt_conveyor_motor import ARRANQUE, F_EXX
    from .engineering.bolts import bolt_shear_capacity_n

    t_arr = ARRANQUE * par_salida_nm * 1e3                 # N·mm
    f = t_arr / r_mm
    sigma = f * raiz_mm / (t_mm * ancho_mm ** 2 / 6.0)
    v_rd = bolt_shear_capacity_n(PERNO_ANCLAJE)
    # cordón del soporte (anillo de Ø D como línea): flexión + corte
    s_w = math.pi * D_SOPORTE ** 2 / 4.0
    fw = f * voladizo_mm / s_w + f / (math.pi * D_SOPORTE)
    tau = fw / GARGANTA_SOPORTE
    out = {"par_arranque_nm": round(t_arr / 1e3, 1), "fuerza_anclaje_n": round(f, 1),
           "sigma_brazo_mpa": round(sigma, 1), "sigma_adm_mpa": round(0.6 * FY_A36, 1),
           "corte_perno_n": round(f, 1), "corte_perno_adm_n": round(v_rd, 1),
           "tau_soldadura_mpa": round(tau, 1), "tau_adm_mpa": round(0.30 * F_EXX, 1),
           "norma": "AISC 360 J2.4 (cordón) · EN 1993-1-8 tabla 3.4 (perno) · σ ≤ 0,6·f_y; par "
                    "de arranque: criterio de diseño (2 × nominal)"}
    out["ok"] = sigma <= 0.6 * FY_A36 and f <= v_rd and tau <= 0.30 * F_EXX
    return out
