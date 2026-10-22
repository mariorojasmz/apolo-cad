"""Reglas del transportador de rodillos HECHO A MANO (`rodillos_a_mano`, F6 de
puerta-de-publicacion): las de `rules.conveyor_engineering_check` con dos cambios, por modo de
falla y no por máquina. PURO: recibe el dict del detector con lo MEDIDO de sus rodillos
(`rodillos_a_mano_medida`).

- **Capacidad de rodillo** = mín(rodamientos, eje) calculada de lo modelado, como la plantilla
  (`rodillos_cadena_reglas._capacidad`) pero con SUS medidas:
  - rodamientos: P por rodamiento = (carga por rodillo + lo que gira) · g / n; rpm = v/(π·Ø);
    L10h contra `L10_TARGET_H` (aviso) y `L10_MIN_H` (error), ISO 281;
  - eje: viga simplemente apoyada en el bastidor con P/n en cada rodamiento (el camino real de la
    carga: tubo → rodamientos → eje fijo → bastidor; el peso propio del eje y la tracción de la
    cadena, despreciables con la rodadura de un transportador de paquetes, no entran):
    σ = M/(π·d³/32) ≤ 0.5·σy (el criterio de eje del repo, más estricto que ASME B106.1M; > σy
    error) y la DESALINEACIÓN del rodamiento: el ángulo entre el eje (que flecta) y el tubo (≈ 100
    veces más rígido: sigue la cuerda entre sus rodamientos) ≤ 10′ (0.0029 rad), el tope del
    rango que admite un rígido de bolas según SKF (2′–10′); sobre 15′ (0.0044 rad, lo máximo que
    tolera un rígido de bolas con juego C4 en el diseño de rodillos de transportador, Bulk Solids
    Handling) es error. Calibrado para que un rodillo de mercado pase: con el apoyo a 15 mm del
    rodamiento, un Ø12 de 500 mm con 25 kg da ≈ 8′. La flecha del centro va de referencia: lo
    que daña el rodamiento es el ángulo, no la flecha. CEMA no fija este límite para rodillos de
    paquetes.
  - Sin un dato real (sin eje que lo atraviese, sin apoyos a los dos lados, sin rodamiento
    reconocible, sin velocidad en la ficha) sale AVISO con el motivo: la capacidad no se inventa.
- **Motor** con el método de la plantilla (`rodillos_cadena.potencia_requerida`: rodadura 5 %,
  arranque ×1.5, η por lazo de cadena y reductor) con el transportador LLENO de paquetes, la masa
  medida de los rodillos y la velocidad de la ficha; FS = P_motor / P_requerida (FS < 1 error,
  < 1.2 aviso). Se llama «motor», como en la plantilla: `calidad/vida_util` le aplica el mismo
  margen de arranque (×1.5) en `vida.factor_servicio`.
"""

from __future__ import annotations

import math

from .engineering.bearings import L10_MIN_H, L10_TARGET_H, l10_hours
from .rules import _check

G = 9.81
THETA_OK = 10.0 / 60.0 * math.pi / 180.0      # 10′ ≈ 0.0029 rad
THETA_MAX = 15.0 / 60.0 * math.pi / 180.0     # 15′ ≈ 0.0044 rad
FS_AVISO = 1.2
_NORMA_CAP = ("ISO 281 (L10) · eje: σ ≤ 0.5·σy (criterio de diseño, más estricto que ASME "
              "B106.1M) y desalineación del rodamiento ≤ 10′ (rígido de bolas: SKF 2′–10′)")
_ORDEN = {"ok": 0, "aviso": 1, "error": 2}


def viga_apoyada(apoyos: tuple[float, float], cargas: list[tuple[float, float]], d: float,
                 e_mpa: float, n: int = 2000) -> dict:
    """Eje macizo Ø`d` (mm) simplemente apoyado en `apoyos` (s, mm) con cargas puntuales
    `cargas` [(s, N)] hacia abajo, dentro del vano o en voladizo. Devuelve el momento máximo
    (N·mm), la pendiente y el desplazamiento en cada carga (rad y mm, con signo: + arriba) y la
    flecha máxima (mm). Integra M/EI dos veces (M lineal por tramos: trapecios finos) con w = 0
    en los apoyos."""
    a, b = apoyos
    rb = sum(f * (s - a) for s, f in cargas) / (b - a)
    fuerzas = [(a, sum(f for _s, f in cargas) - rb), (b, rb)] + [(s, -f) for s, f in cargas]

    def momento(x: float) -> float:  # + = el eje se curva hacia arriba (cóncavo, «sonrisa»)
        return sum(p * (x - s) for s, p in fuerzas if s < x)

    ei = e_mpa * math.pi * d ** 4 / 64.0
    s0 = min(s for s, _p in fuerzas)
    h = (max(s for s, _p in fuerzas) - s0) / n
    xs = [s0 + i * h for i in range(n + 1)]
    kap = [momento(x) / ei for x in xs]
    th, w = [0.0], [0.0]
    for i in range(n):
        th.append(th[-1] + (kap[i] + kap[i + 1]) * h / 2.0)
        w.append(w[-1] + (th[i] + th[i + 1]) * h / 2.0)

    def interp(serie, x):
        j = min(n - 1, max(0, int((x - s0) / h)))
        t = (x - xs[j]) / h
        return serie[j] + t * (serie[j + 1] - serie[j])

    th0 = -(interp(w, b) - interp(w, a)) / (b - a)
    w0 = -interp(w, a) - th0 * (a - s0)
    flecha = max(abs(wi + th0 * (x - s0) + w0) for x, wi in zip(xs, w))
    return {"m_max": max(abs(momento(s)) for s, _p in fuerzas),
            "pendientes": [interp(th, s) + th0 for s, _f in cargas],
            "w": [interp(w, s) + th0 * (s - s0) + w0 for s, _f in cargas],
            "flecha": flecha}


def desalineacion(viga: dict, cargas: list[tuple[float, float]]) -> float:
    """Ángulo (rad) entre el eje y el TUBO en el rodamiento peor: el tubo (≈ 100 veces más rígido
    que el eje) sigue la cuerda entre sus rodamientos extremos; con uno solo, el eje contra la
    horizontal."""
    th, w, ss = viga["pendientes"], viga["w"], [s for s, _f in cargas]
    i, j = ss.index(min(ss)), ss.index(max(ss))
    cuerda = (w[j] - w[i]) / (ss[j] - ss[i]) if ss[j] > ss[i] else 0.0
    return max(abs(t - cuerda) for t in th)


def _capacidad_rodillo(r: dict, p_kg: float, v: float) -> tuple[str, float | None, dict, str]:
    """(estado, fs, calc, detalle) de UN rodillo medido."""
    from .catalog import CATALOG

    m_rod = float(r.get("masa_kg") or 0.0)
    eje, rods = r["eje"], r["rodamientos"]
    p_tot = (p_kg + m_rod) * G
    f = p_tot / len(rods)
    c_kn = min(float(CATALOG[x["ref"]].specs["C_kN"]) for x in rods)
    rpm = v * 60000.0 / (math.pi * r["od"])
    vida = l10_hours(c_kn, f / 1000.0, rpm)
    a, b = r["apoyos"]
    cargas = [(x["s"], f) for x in rods]
    viga = viga_apoyada((a, b), cargas, eje["d"], eje["E"])
    sigma = viga["m_max"] / (math.pi * eje["d"] ** 3 / 32.0)
    theta = desalineacion(viga, cargas)
    sy = float(eje["sy"])
    k_l10 = (vida / L10_TARGET_H) ** (1.0 / 3.0) if not math.isinf(vida) else math.inf
    k_sig = 0.5 * sy / sigma if sigma > 0 else math.inf
    k_th = THETA_OK / theta if theta > 0 else math.inf
    fs = min(k_l10, k_sig, k_th)
    cap = p_tot * fs / G - m_rod if not math.isinf(fs) else math.inf
    refs = sorted({x["ref"] for x in rods})
    vida_txt = "L10 > 10⁶ h" if vida > 1e6 else f"L10 = {vida:,.0f} h"
    calc = {"titulo": "Capacidad de rodillo (a medida)",
            "entradas": {
                "carga": f"{p_kg:.1f} kg/rodillo + lo que gira {m_rod:.2f} kg",
                "rodamientos": f"{len(rods)} × {'/'.join(refs)} (C = {c_kn:g} kN) a s = "
                               + ", ".join(f"{x['s']:g}" for x in rods) + " mm",
                "eje": f"Ø{eje['d']:g} {eje['material']} (σy {sy:g} MPa, E {eje['E']:g} MPa)",
                "apoyos": f"s = {a:g} / {b:g} mm (vano {b - a:.0f} mm: "
                          + " / ".join((r.get("nombres") or {}).get("apoyos") or []) + ")",
                "rpm del rodillo": f"{rpm:.0f} (v {v:g} m/s, Ø{r['od']:g})",
                "hipótesis": "eje fijo simplemente apoyado; carga en los rodamientos; sin peso "
                             "propio del eje ni tracción de la cadena"},
            "formula": "P = (m_paq/n + m_rod)·g; L10h = (C/(P/n_r))³·10⁶/(60·n_rpm); "
                       "σ = M/(π·d³/32); θ = pendiente del eje contra el tubo en el rodamiento",
            "sustitucion": f"P = {p_tot:.0f} N; P/n_r = {f:.0f} N; M = {viga['m_max']:.0f} N·mm",
            "resultado": (f"{vida_txt}; σ = {sigma:.0f} MPa; θ = {theta:.5f} rad "
                          f"({theta * 180 / math.pi * 60:.1f}′); flecha {viga['flecha']:.3f} mm; "
                          f"capacidad {cap:.0f} kg/rodillo"),
            "criterio": f"L10 ≥ {L10_TARGET_H:.0f} h · σ ≤ 0.5·σy = {0.5 * sy:g} MPa · "
                        f"θ ≤ 10′ ({THETA_OK:.4f} rad)",
            "fs": round(fs, 2) if not math.isinf(fs) else None, "norma": _NORMA_CAP}
    det = (f"{p_kg:.1f} kg/rodillo sobre {len(rods)} × {'/'.join(refs)} y eje Ø{eje['d']:g}: "
           f"{vida_txt}, σ = {sigma:.0f} MPa, desalineación {theta * 180 / math.pi * 60:.1f}′ "
           f"(capacidad {cap:.0f} kg/rodillo).")
    if vida < L10_MIN_H or sigma > sy or theta > THETA_MAX:
        estado = "error"
    elif vida < L10_TARGET_H or sigma > 0.5 * sy or theta > THETA_OK:
        estado = "aviso"
    else:
        estado = "ok"
    return estado, fs, calc, det


def capacidad_a_medida(conveyor: dict, carga_kg: float, apoyos: int,
                       velocidad_m_s: float) -> dict:
    """«capacidad de rodillo» de un rodillo SIN ficha de capacidad: de sus rodamientos y su eje
    MEDIDOS; el peor rodillo del lecho manda. Sin un dato real → aviso con el motivo."""
    ref = conveyor.get("rodillo", "?")
    p = carga_kg / max(1, apoyos)
    medidos = conveyor.get("rodillos_medidos") or []
    motivo = next((m["motivo"] for m in medidos if m.get("motivo")), None)
    if not medidos:
        motivo = "no se midió el rodillo"
    elif motivo is None and not velocidad_m_s:
        motivo = "la ficha no tiene velocidad: sin rpm no se calcula la vida L10"
    if motivo is not None:
        calc = {"titulo": "Capacidad de rodillo",
                "entradas": {"carga por paquete": f"{carga_kg:g} kg",
                             "apoyos": f"{max(1, apoyos)}",
                             "rodillo": f"{ref} a medida (sin capacidad de ficha)"},
                "formula": "P = carga / n_apoyos",
                "sustitucion": f"P = {carga_kg:g} / {max(1, apoyos)}",
                "resultado": f"P = {p:.1f} kg/rodillo",
                "criterio": "P ≤ capacidad del rodillo (rodamiento L10 y eje): sin dato, no se "
                            "verifica", "fs": None, "norma": "criterio de diseño"}
        return _check("capacidad de rodillo", "aviso",
                      f"{p:.1f} kg/rodillo sobre un rodillo a medida ({ref}): no se calcula su "
                      f"capacidad porque {motivo}.",
                      "Modela su eje pasante y su rodamiento de catálogo (o nómbralo con su serie, "
                      "«Rodamiento 6201»), o usa un rodillo de catálogo (categoría «rodillos»).",
                      calc=calc)
    peor = max((_capacidad_rodillo(m, p, velocidad_m_s) for m in medidos),
               key=lambda x: (_ORDEN[x[0]], -(x[1] if x[1] is not None else math.inf)))
    estado, _fs, calc, det = peor
    return _check("capacidad de rodillo", estado, det,
                  None if estado == "ok" else
                  "Reparte el paquete en más rodillos (paso menor), sube el eje o el rodamiento "
                  "(serie mayor) o acorta el vano entre los apoyos del eje.", calc=calc)


def motor_a_mano(conveyor: dict, carga_kg: float, largo_paquete_mm: float,
                 velocidad_m_s: float) -> dict:
    """«motor» con el método de la plantilla (ver el docstring del módulo)."""
    from .rodillos_cadena import potencia_requerida

    n = int(conveyor.get("n_rodillos") or 0)
    paso = float(conveyor.get("paso") or 0.0)
    largo = float(conveyor.get("largo") or 0.0) + paso  # el lecho cubre n pasos
    n_paq = max(1, math.floor(largo / largo_paquete_mm)) if largo_paquete_mm else 1
    q = n_paq * carga_kg
    m_rod = float(conveyor.get("masa_rodillos_kg") or 0.0)
    p_motor = conveyor.get("motor_kW")
    motor = conveyor.get("motor", "?")
    if not p_motor or not velocidad_m_s or n < 1:
        falta = "potencia del motor (ficha o placa en el nombre)" if not p_motor else "velocidad"
        return _check("motor", "aviso", f"{motor}: no se calcula su carga, falta la {falta}.",
                      "Declara la velocidad en la ficha y usa un motorreductor de catálogo.")
    p_req = potencia_requerida(q, m_rod, velocidad_m_s, n)
    fs = float(p_motor) / p_req
    calc = {"titulo": "Potencia del motor", "entradas": {
                "carga": f"{n_paq} × {carga_kg:g} kg (lleno de paquetes) + rodillos {m_rod:.0f} kg "
                         f"(medidos, {n} rodillos)",
                "v": f"{velocidad_m_s:.3f} m/s", "motor": f"{motor} ({float(p_motor):g} kW)"},
            "formula": "P = 1.5·μ·(Q + m_rodillos)·g·v / (η_lazos·η_reductor)",
            "sustitucion": f"P = 1.5·0.05·{q + m_rod:.0f}·9.81·{velocidad_m_s:.3f} / η",
            "resultado": f"P = {p_req:.3f} kW → FS {fs:.2f}",
            "criterio": f"FS ≥ 1 (aviso bajo {FS_AVISO:g})", "fs": round(fs, 2),
            "norma": "criterio de diseño (rodadura 5 %, arranque ×1.5, η lazo 0.98, reductor 0.85)"}
    estado = "error" if fs < 1.0 else ("aviso" if fs < FS_AVISO else "ok")
    return _check("motor", estado, f"{motor}: pide {p_req:.3f} kW de {float(p_motor):g} kW "
                  f"(FS {fs:.2f}).", "Elige un motorreductor mayor." if fs < FS_AVISO else None,
                  calc=calc)


def reglas_a_mano(conveyor: dict, carga_kg: float, largo_paquete_mm: float,
                  velocidad_m_s: float, ancho_paquete_mm: float | None = None) -> list[dict]:
    """Las reglas de `conveyor_engineering_check` con el «motor» de arriba en lugar de su
    «motorización» (la capacidad ya sale de `capacidad_a_medida`: el rodillo no tiene ficha)."""
    from .rules import conveyor_engineering_check

    base = conveyor_engineering_check({**conveyor, "a_mano": False}, carga_kg, largo_paquete_mm,
                                      velocidad_m_s, ancho_paquete_mm)
    return [motor_a_mano(conveyor, carga_kg, largo_paquete_mm, velocidad_m_s)
            if r.get("regla") == "motorización" else r for r in base]
