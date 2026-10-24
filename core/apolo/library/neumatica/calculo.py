"""Cálculo neumático de la memoria (plan V8.9 D10): cada función devuelve su bloque `calc`.

Funciones PURAS sobre números (y, donde se dice, sobre una `FichaNeumatica`):
  - `fuerzas`: teórica de avance (p·A) y retroceso (p·A_anular) y la efectiva con la fricción;
  - `consumo_ciclo`: aire libre por ciclo en NL (ANR, ISO 8778) por balance ISOTERMO de masa, con
    los volúmenes muertos y los tubos, y por minuto con la cadencia que se declare (D3: la
    isoterma es la fórmula de catálogo; la co-simulación sale ~4 % abajo, F0 § 1);
  - `caudal_pico` y `verificar_caudal`: lo que pide el cilindro a su velocidad contra lo que pasa
    un componente (ISO 6358-1) con la caída de presión que se acepta;
  - `regimen`: la cota a mano de la velocidad y el tiempo de carrera con el escape en bloqueo
    sónico, v = C·p_ANR / A_escape (D3, F0 § 1);
  - `pandeo_vastago`: Euler con el caso de su montaje (Johnson si se da fy y la esbeltez es baja);
  - `energia_impacto`: ½·m·v² al fin de carrera contra la admisible de la amortiguación;
  - `demanda_aire`: la de la máquina, más un % de fugas DECLARADO (el dato para el compresor).

Convenciones: presiones manométricas en bar (`_g` o «p_bar_g»), áreas en mm², volúmenes en cm³,
fuerzas en N. La presión ambiente, si no se declara, es la atmósfera estándar (ISO 2533) y se
lista en `hipotesis`. Estados como en `engineering/`: «ok», «aviso», «error».
"""

from __future__ import annotations

import math

from .iso6358 import P_ANR_BAR, P_ATM_ESTANDAR_BAR, caudal_anr, velocidad_regimen_sonica

#: Módulo de elasticidad del acero del vástago (EN 1993-1-1 § 3.2.6: E = 210 000 N/mm²).
E_ACERO_MPA = 210000.0
#: Factor de seguridad mínimo contra la carga crítica de pandeo: criterio de diseño, el mismo
#: `BUCKLING_FS` de `engineering/buckling.py` (Euler ignora imperfecciones: margen amplio).
FS_PANDEO = 3.0
#: Casos de Euler → factor de longitud K (Lk = K·L): 1 empotrado-libre, 2 articulado-articulado,
#: 3 empotrado-articulado, 4 empotrado-empotrado (Euler; la numeración de los catálogos de
#: cilindros).
CASOS_EULER = {1: 2.0, 2: 1.0, 3: 0.7, 4: 0.5}
#: Sin fy del vástago, por debajo de esta esbeltez Euler puede no valer: λc = π·√(2E/fy) = 100
#: para fy ≈ 415 MPa (criterio de diseño); se pide fy para pasar a Johnson.
LAMBDA_SIN_FY = 100.0

_HIP_PATM = "p_atm = 1,01325 bar (atmósfera estándar ISO 2533): el proyecto no declaró la de su sitio"


def _hip_patm(p_atm: float | None) -> tuple[float, list[str]]:
    return (P_ATM_ESTANDAR_BAR, [_HIP_PATM]) if p_atm is None else (float(p_atm), [])


def _res(titulo: str, valor: dict, estado: str, hipotesis: list[str], **calc) -> dict:
    return {"titulo": titulo, "valor": valor, "estado": estado, "hipotesis": hipotesis,
            "calc": {"titulo": titulo, **calc}}


def areas(D_mm: float, d_mm: float) -> tuple[float, float, float]:
    """(A del pistón, A anular del lado del vástago, a del vástago) en mm²."""
    A = math.pi * D_mm ** 2 / 4.0
    a = math.pi * d_mm ** 2 / 4.0
    return A, A - a, a


def fuerzas(D_mm: float, d_mm: float, p_bar_g: float, *, friccion_N: float | None = None,
            friccion_pct: float | None = None) -> dict:
    """Fuerza teórica de avance F = p·A y de retroceso F = p·A_anular (la otra cámara a la
    atmósfera), y la efectiva restando la fricción de los sellos (N de la ficha o % de la teórica)."""
    if (friccion_N is None) == (friccion_pct is None):
        raise ValueError("declara UNA fricción: friccion_N o friccion_pct")
    A, Ab, _a = areas(D_mm, d_mm)
    p = p_bar_g * 0.1  # bar → N/mm²
    fa, fr = p * A, p * Ab
    if friccion_N is not None:
        ea, er = fa - friccion_N, fr - friccion_N
        fric = f"{friccion_N:g} N"
    else:
        ea, er = fa * (1 - friccion_pct / 100), fr * (1 - friccion_pct / 100)
        fric = f"{friccion_pct:g} % de la teórica"
    return _res(
        f"Fuerza del cilindro Ø{D_mm:g}/{d_mm:g}",
        {"F_avance_N": fa, "F_retroceso_N": fr, "F_avance_ef_N": ea, "F_retroceso_ef_N": er},
        "ok", [],
        entradas={"pistón": f"Ø{D_mm:g} mm (A = {A:.1f} mm²)",
                  "vástago": f"Ø{d_mm:g} mm (A anular = {Ab:.1f} mm²)",
                  "presión": f"{p_bar_g:g} bar manométricos", "fricción": fric},
        formula="F_av = p·A · F_ret = p·(A − a) · F_ef = F − F_fricción",
        sustitucion=f"F_av = {p:g}·{A:.1f} = {fa:.1f} N · F_ret = {p:g}·{Ab:.1f} = {fr:.1f} N",
        resultado=f"avance {fa:.0f} N ({ea:.0f} N efectiva) · retroceso {fr:.0f} N ({er:.0f} N efectiva)",
        criterio="fuerza teórica de catálogo con la otra cámara a la atmósfera", fs=None,
        norma="criterio de diseño (fórmula de catálogo; ISO 15552/6432 fijan cotas, no fuerzas)")


def fuerzas_de_ficha(ficha, p_bar_g: float) -> dict:
    """`fuerzas` con los datos de una `FichaNeumatica` de cilindro; lo `a_confirmar` va a hipótesis."""
    m = ficha.modelo
    r = fuerzas(m["D_mm"], m["d_mm"], p_bar_g, friccion_N=m.get("friccion_N"),
                friccion_pct=m.get("friccion_pct"))
    r["hipotesis"] += [f"{k} de la ficha a confirmar" for k in ficha.a_confirmar if k.startswith("friccion")]
    if not m["p_min_bar"] <= p_bar_g <= m["p_max_bar"]:
        r["estado"] = "error"
        r["calc"]["criterio"] += f" · presión dentro de {m['p_min_bar']:g}–{m['p_max_bar']:g} bar de la ficha"
    return r


def volumen_tubo_cm3(D_int_mm: float, largo_m: float) -> float:
    """Volumen interior (cm³) de un tubo: π·Di²/4 [mm²] · L [m] (mm²·m = cm³)."""
    return math.pi * D_int_mm ** 2 / 4.0 * largo_m


def consumo_carrera_nl(A_mm2: float, carrera_mm: float, V0_cm3: float, p_bar_g: float,
                       p_atm: float = P_ATM_ESTANDAR_BAR) -> float:
    """Aire libre (NL ANR) que entra a UNA cámara en una carrera, por balance isotermo de masa:
    empieza con V0 (muerto + tubo) a la atmósfera y termina con V0 + A·s a la red:
    ΔV_ANR = ((p_atm + p)·(V0 + A·s) − p_atm·V0) / p_ANR."""
    V_fin = V0_cm3 + A_mm2 * carrera_mm / 1000.0
    return ((p_atm + p_bar_g) * V_fin - p_atm * V0_cm3) / P_ANR_BAR / 1000.0


def consumo_ciclo(D_mm: float, d_mm: float, carrera_mm: float, p_bar_g: float, *,
                  V_muerto_A_cm3: float, V_muerto_B_cm3: float, V_tubo_A_cm3: float = 0.0,
                  V_tubo_B_cm3: float = 0.0, ciclos_min: float | None = None,
                  p_atm: float | None = None, simple_efecto: bool = False) -> dict:
    """Consumo por ciclo doble (avance + retroceso) en NL ANR y por minuto con la cadencia."""
    patm, hip = _hip_patm(p_atm)
    A, Ab, _a = areas(D_mm, d_mm)
    V0A, V0B = V_muerto_A_cm3 + V_tubo_A_cm3, V_muerto_B_cm3 + V_tubo_B_cm3
    qa = consumo_carrera_nl(A, carrera_mm, V0A, p_bar_g, patm)
    qr = 0.0 if simple_efecto else consumo_carrera_nl(Ab, carrera_mm, V0B, p_bar_g, patm)
    ciclo = qa + qr
    valor = {"avance_NL": qa, "retroceso_NL": qr, "ciclo_NL": ciclo}
    res = f"{ciclo:.3f} NL por ciclo (avance {qa:.3f} + retroceso {qr:.3f})"
    if ciclos_min is not None:
        valor["NL_min"] = ciclo * ciclos_min
        res += f" · {valor['NL_min']:.1f} NL/min a {ciclos_min:g} ciclos/min"
    hip.append("isoterma a 20 °C (la fórmula de catálogo; la co-simulación sin enfriamiento da ~4 % menos)")
    return _res(
        f"Consumo de aire Ø{D_mm:g}/{d_mm:g} carrera {carrera_mm:g}", valor, "ok", hip,
        entradas={"áreas": f"A = {A:.1f} mm², A anular = {Ab:.1f} mm²", "carrera": f"{carrera_mm:g} mm",
                  "volumen muerto + tubo": f"A {V0A:g} cm³ · B {V0B:g} cm³",
                  "presión": f"{p_bar_g:g} bar manométricos (p_atm {patm:g} bar)"},
        formula="ΔV_ANR = ((p_atm + p)·(V0 + A·s) − p_atm·V0) / p_ANR, por cámara",
        sustitucion=(f"avance: (({patm:g} + {p_bar_g:g})·({V0A:g} + {A * carrera_mm / 1000:.2f}) − "
                     f"{patm:g}·{V0A:g}) / {P_ANR_BAR:g} = {qa * 1000:.1f} cm³"),
        resultado=res, criterio="aire libre en NL ANR (ISO 8778: 20 °C, 100 kPa)", fs=None,
        norma="ISO 8778 (aire de referencia) · criterio de diseño (balance isotermo)")


def caudal_pico(A_mm2: float, v_m_s: float, p_bar_g: float, p_atm: float = P_ATM_ESTANDAR_BAR) -> float:
    """Caudal ANR (NL/min) que pide la cámara que se llena a la presión de red a velocidad v."""
    return A_mm2 * 1e-6 * v_m_s * 1000.0 * 60.0 * (p_atm + p_bar_g) / P_ANR_BAR


def verificar_caudal(nombre: str, C: float, b: float, q_pico_nl_min: float, p1_bar_g: float,
                     dp_bar: float, *, m: float = 0.5, p_atm: float | None = None) -> dict:
    """¿Pasa el componente el caudal pico con una caída ≤ dp_bar? q = C·p1·φ(p2/p1, b) (ISO 6358-1)
    con p2 = p1 − dp. `dp_bar` es el criterio que declara quien verifica."""
    patm, hip = _hip_patm(p_atm)
    p1 = p1_bar_g + patm
    q = caudal_anr(C, b, p1, p1 - dp_bar, m=m) * 60.0
    estado = "ok" if q >= q_pico_nl_min else "aviso"
    return _res(
        f"Caudal de {nombre}", {"q_disponible_NL_min": q, "q_pico_NL_min": q_pico_nl_min}, estado, hip,
        entradas={"C": f"{C:g} dm³/(s·bar)", "b": f"{b:g}", "p1": f"{p1_bar_g:g} bar man.",
                  "caída aceptada": f"{dp_bar:g} bar", "pico pedido": f"{q_pico_nl_min:.0f} NL/min"},
        formula="q = C·p1·√(1 − ((p2/p1 − b)/(1 − b))²)^m·… (ISO 6358-1), p2 = p1 − Δp",
        sustitucion=f"q = {C:g}·{p1:.3f}·φ({(p1 - dp_bar) / p1:.3f}) = {q / 60:.2f} dm³/s = {q:.0f} NL/min",
        resultado=f"{q:.0f} NL/min disponibles contra {q_pico_nl_min:.0f} NL/min de pico",
        criterio=f"q disponible ≥ pico con Δp ≤ {dp_bar:g} bar", fs=None, norma="ISO 6358-1:2013")


def regimen(C_escape: float, A_escape_mm2: float, carrera_mm: float, *, b: float,
            p_camara_bar_g: float | None = None, p_atm: float | None = None) -> dict:
    """Cota a mano de la velocidad y del tiempo de carrera con el ESCAPE en bloqueo sónico:
    v = C·p_ANR / A_escape, t = s / v (D3). Vale si la cámara que escapa está sobre p_atm/b
    (bloqueo); con `p_camara_bar_g` se comprueba, sin ella se declara como hipótesis."""
    patm, hip = _hip_patm(p_atm)
    v = velocidad_regimen_sonica(C_escape, A_escape_mm2)
    t = carrera_mm / 1000.0 / v
    p_bloqueo = patm / b if b > 0 else math.inf
    estado = "ok"
    if p_camara_bar_g is None:
        hip.append(f"escape en bloqueo sónico: la cámara sobre p_atm/b = {p_bloqueo:.2f} bar abs")
    elif p_camara_bar_g + patm < p_bloqueo:
        estado = "aviso"
        hip.append(f"la cámara a {p_camara_bar_g:g} bar man. no bloquea (p_atm/b = {p_bloqueo:.2f} bar abs): "
                   "la cota sobreestima la velocidad")
    hip.append("régimen permanente: sin la aceleración ni la amortiguación de fin de carrera")
    return _res(
        "Velocidad de régimen con escape sónico", {"v_m_s": v, "t_s": t}, estado, hip,
        entradas={"C del escape": f"{C_escape:g} dm³/(s·bar)", "área que escapa": f"{A_escape_mm2:.1f} mm²",
                  "carrera": f"{carrera_mm:g} mm", "b": f"{b:g}"},
        formula="v = C·p_ANR / A_escape · t = s / v",
        sustitucion=(f"v = {C_escape:g} dm³/(s·bar) · {P_ANR_BAR:g} bar / {A_escape_mm2:.1f} mm² = "
                     f"{C_escape:g}·1000/{A_escape_mm2:.1f} = {v:.3f} m/s"),
        resultado=f"v = {v:.3f} m/s · t = {t:.3f} s", criterio="cota de régimen (D3)", fs=None,
        norma="ISO 6358-1:2013 (caudal en bloqueo) · ISO 8778 (ANR)")


def pandeo_vastago(d_mm: float, largo_mm: float, caso: int, F_N: float, *, E_mpa: float = E_ACERO_MPA,
                   fs_min: float = FS_PANDEO, fy_mpa: float | None = None) -> dict:
    """Pandeo del vástago como columna de largo libre `largo_mm` con el caso de Euler de su
    montaje. Pcr = π²·E·I/(K·L)² (I = π·d⁴/64); con fy y λ < λc = π·√(2E/fy), Johnson:
    Pcr = A·fy·(1 − fy·λ²/(4π²·E))."""
    if caso not in CASOS_EULER:
        raise ValueError(f"caso de Euler 1–4, llegó {caso}")
    K = CASOS_EULER[caso]
    I = math.pi * d_mm ** 4 / 64.0
    A = math.pi * d_mm ** 2 / 4.0
    lk = K * largo_mm
    lam = lk / (d_mm / 4.0)
    hip = [f"caso {caso} de Euler (K = {K:g}) por el montaje", f"E = {E_mpa:g} MPa (EN 1993-1-1)"]
    metodo = "Euler"
    pcr = math.pi ** 2 * E_mpa * I / lk ** 2
    estado = "ok"
    if fy_mpa is not None:
        lam_c = math.pi * math.sqrt(2 * E_mpa / fy_mpa)
        if lam < lam_c:
            metodo = "Johnson"
            pcr = A * fy_mpa * (1 - fy_mpa * lam ** 2 / (4 * math.pi ** 2 * E_mpa))
    elif lam < LAMBDA_SIN_FY:
        estado = "aviso"
        hip.append(f"λ = {lam:.0f} < {LAMBDA_SIN_FY:g}: Euler puede sobreestimar; declara fy del vástago (Johnson)")
    fs = pcr / F_N if F_N > 0 else math.inf
    if fs < fs_min:
        estado = "error"
    return _res(
        f"Pandeo del vástago Ø{d_mm:g}", {"Pcr_N": pcr, "F_adm_N": pcr / fs_min, "lambda": lam, "fs": fs},
        estado, hip,
        entradas={"vástago": f"Ø{d_mm:g} mm (I = {I:.1f} mm⁴)", "largo libre": f"{largo_mm:g} mm",
                  "caso": f"{caso} (K = {K:g}, Lk = {lk:g} mm, λ = {lam:.0f})", "fuerza": f"{F_N:.0f} N"},
        formula=("Pcr = π²·E·I/(K·L)²" if metodo == "Euler" else "Pcr = A·fy·(1 − fy·λ²/(4π²E))"),
        sustitucion=(f"Pcr = π²·{E_mpa:g}·{I:.1f}/{lk:g}² = {pcr:.0f} N" if metodo == "Euler"
                     else f"Pcr = {A:.1f}·{fy_mpa:g}·(1 − {fy_mpa:g}·{lam:.1f}²/(4π²·{E_mpa:g})) = {pcr:.0f} N"),
        resultado=f"Pcr = {pcr:.0f} N ({metodo}), admisible {pcr / fs_min:.0f} N, FS = {fs:.2f}",
        criterio=f"FS ≥ {fs_min:g} (criterio de diseño)", fs=round(fs, 2),
        norma=f"{metodo} (columna; casos de Euler de los catálogos) · criterio de diseño")


def masa_movil_kg(modelo: dict, carrera_mm: float, masa_carga_kg: float = 0.0) -> float:
    """Masa que llega al fin de carrera: la móvil del cilindro (base + por mm) más la carga."""
    return modelo["masa_movil_base_kg"] + modelo["masa_movil_por_mm_kg"] * carrera_mm + masa_carga_kg


def energia_impacto(m_kg: float, v_m_s: float, E_adm_J: float) -> dict:
    """E = ½·m·v² al fin de carrera contra la admisible de la amortiguación (D9: error si la pasa)."""
    E = 0.5 * m_kg * v_m_s ** 2
    estado = "ok" if E <= E_adm_J else "error"
    return _res(
        "Energía al fin de carrera", {"E_J": E, "E_adm_J": E_adm_J}, estado, [],
        entradas={"masa móvil + carga": f"{m_kg:g} kg", "velocidad al llegar": f"{v_m_s:g} m/s",
                  "admisible": f"{E_adm_J:g} J (ficha)"},
        formula="E = ½·m·v²", sustitucion=f"E = ½·{m_kg:g}·{v_m_s:g}² = {E:.3f} J",
        resultado=f"{E:.3f} J contra {E_adm_J:g} J admisibles",
        criterio="E ≤ admisible de la amortiguación; si no, amortiguador externo o menos velocidad",
        fs=round(E_adm_J / E, 2) if E > 0 else None, norma="criterio de diseño (dato de ficha del fabricante)")


def demanda_aire(consumos: list[tuple[str, float, float]], fugas_pct: float) -> dict:
    """Demanda de la máquina en NL/min: Σ (NL por ciclo · ciclos/min) · (1 + fugas). `fugas_pct`
    es una hipótesis que DECLARA quien calcula (no hay valor por defecto)."""
    base = sum(nl * cpm for _n, nl, cpm in consumos)
    total = base * (1 + fugas_pct / 100.0)
    return _res(
        "Demanda de aire de la máquina", {"NL_min": total, "sin_fugas_NL_min": base}, "ok",
        [f"fugas = {fugas_pct:g} % declarado (hipótesis)"],
        entradas={n: f"{nl:.3f} NL/ciclo × {cpm:g} ciclos/min" for n, nl, cpm in consumos},
        formula="Q = Σ(V_ciclo · n) · (1 + fugas)",
        sustitucion=f"Q = {base:.1f} · (1 + {fugas_pct:g}/100) = {total:.1f} NL/min",
        resultado=f"{total:.1f} NL/min ({total / 1000:.3f} Nm³/min ANR)",
        criterio="el dato para elegir el compresor y la red", fs=None, norma="ISO 8778 (ANR) · criterio de diseño")
