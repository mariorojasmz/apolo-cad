"""Vuelco por las fuerzas de TRABAJO declaradas (plan puerta-fuera-de-catalogo, D8). Puro: recibe
la base de apoyo, el centro de gravedad, el peso, el contorno de la máquina y las fuerzas de los
requisitos (`requisitos.requisitos_vuelco`); la regla de siempre (COG dentro de la base con margen)
sigue en `report_estructura._tipping_check`, que llama a ésta cuando hay fuerzas declaradas.

Para cada arista de la base (casco convexo de los apoyos), el giro sobre ella:
- **estabilizante**: el peso propio por su brazo (COG hasta la arista, hacia dentro) × 0,9;
- **desestabilizante**: la fuerza horizontal F_h, perpendicular a la arista y hacia fuera, por su
  altura sobre el piso, × 1,5; la carga de borde P_b en el punto del contorno de la máquina más
  allá de la arista (el canto de la superficie que vuela), × 1,5; el peso propio, si su COG cae
  fuera, × 1,1;
- la carga útil NO estabiliza (acción variable favorable × 0): el caso que el revisor halló fue la
  mesa VACÍA empujada.

Coeficientes: EN 1990:2002 tabla A1.2(A) (equilibrio estático, EQU): γG,sup 1,10, γG,inf 0,90,
γQ 1,50 desfavorable y 0 favorable. Criterio: M_estab,d ≥ M_desest,d en la arista más
desfavorable (FS = M_estab,d / M_desest,d ≥ 1). La altura de F_h, si no se declara, es la del
punto más alto de la máquina (el brazo más largo posible: conservador, y la regla lo dice).
"""

from __future__ import annotations

import math

GAMMA_G_ESTAB = 0.90
GAMMA_G_DESEST = 1.10
GAMMA_Q = 1.50
NORMA = "EN 1990:2002 tabla A1.2(A) (EQU: γG 0,9 estabilizante / 1,1 desestabilizante, γQ 1,5; " \
        "variable favorable = 0)"
REGLA = "estabilidad al vuelco · fuerzas de trabajo"


def _aristas(base):
    n = len(base)
    for i in range(n):
        a, b = base[i], base[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        lado = math.hypot(dx, dy)
        if lado > 1e-9:
            yield a, b, (dy / lado, -dx / lado)  # normal HACIA FUERA de un casco antihorario


def evaluar(*, base: list, cog_xy: tuple, peso_n: float, contorno: list, altura_max_mm: float,
            fuerzas: dict, carga_util_n: float = 0.0) -> dict:
    """{peor: {arista, brazo_cog, voladizo, m_estab, m_desest, fs}, f_h_limite, altura, ...}."""
    f_h = float(fuerzas.get("fuerza_horizontal_n") or 0.0)
    p_b = float(fuerzas.get("carga_borde_n") or 0.0)
    h = float(fuerzas.get("altura_fuerza_mm") or altura_max_mm)
    peor = None
    for a, b, n in _aristas(base):
        brazo = -((cog_xy[0] - a[0]) * n[0] + (cog_xy[1] - a[1]) * n[1])  # + = dentro
        vuela = max((q[0] - a[0]) * n[0] + (q[1] - a[1]) * n[1] for q in contorno)
        m_est = GAMMA_G_ESTAB * peso_n * max(brazo, 0.0)
        m_des = (GAMMA_Q * f_h * h + GAMMA_Q * p_b * max(vuela, 0.0)
                 + GAMMA_G_DESEST * peso_n * max(-brazo, 0.0))
        fs = m_est / m_des if m_des > 0 else math.inf
        fila = {"arista": (a, b), "brazo_cog": brazo, "voladizo": max(vuela, 0.0),
                "m_estab": m_est, "m_desest": m_des, "fs": fs}
        if peor is None or fs < peor["fs"]:
            peor = fila
    if peor is None:
        return {}
    brazo, vuela = peor["brazo_cog"], peor["voladizo"]
    # la F_h con la que se cae VACÍA (sin coeficientes), y la misma con la carga útil encima
    # (sobre el COG: sólo informativo, la puerta no la cuenta)
    momento_borde = p_b * vuela
    f_lim = max(peso_n * brazo - momento_borde, 0.0) / h if h > 0 else math.inf
    f_lim_carga = max((peso_n + carga_util_n) * brazo - momento_borde, 0.0) / h if h > 0 else math.inf
    return {"peor": peor, "altura_mm": h, "altura_declarada": bool(fuerzas.get("altura_fuerza_mm")),
            "f_h": f_h, "p_b": p_b, "f_h_limite_n": f_lim, "f_h_limite_con_carga_n": f_lim_carga}


def regla(*, base, cog_xy, cog_z, peso_n, contorno, altura_max_mm, fuerzas,
          carga_util_n=0.0) -> dict | None:
    """La regla «estabilidad al vuelco · fuerzas de trabajo» (formato `rules._check`)."""
    from ..rules import _check

    r = evaluar(base=base, cog_xy=cog_xy, peso_n=peso_n, contorno=contorno,
                altura_max_mm=altura_max_mm, fuerzas=fuerzas, carga_util_n=carga_util_n)
    if not r:
        return None
    p = r["peor"]
    (ax, ay), (bx, by) = p["arista"]
    fs = p["fs"]
    h_txt = (f"{r['altura_mm']:.0f} mm" + ("" if r["altura_declarada"] else
                                           " (no declarada: el punto más alto)"))
    calc = {
        "titulo": "Vuelco por las fuerzas de trabajo",
        "entradas": {
            "peso propio": f"{peso_n:.0f} N (COG ({cog_xy[0]:.0f}, {cog_xy[1]:.0f}, {cog_z:.0f}) mm)",
            "fuerza horizontal": f"{r['f_h']:.0f} N a {h_txt}",
            "carga de borde": f"{r['p_b']:.0f} N en el canto que más vuela ({p['voladizo']:.0f} "
                              "mm fuera de la arista)",
            "arista de giro": f"({ax:.0f}, {ay:.0f}) – ({bx:.0f}, {by:.0f}) mm",
            "carga útil": (f"{carga_util_n:.0f} N: no estabiliza (favorable × 0)"
                           if carga_util_n else "no declarada"),
        },
        "formula": "M_estab,d = 0,9·W·b ≥ M_desest,d = 1,5·F_h·h + 1,5·P_b·e (+ 1,1·W·|b| con el "
                   "COG fuera)",
        "sustitucion": (f"M_estab,d = 0,9·{peso_n:.0f}·{max(p['brazo_cog'], 0):.0f} = "
                        f"{p['m_estab'] / 1e3:.1f} N·m; M_desest,d = {p['m_desest'] / 1e3:.1f} N·m"),
        "resultado": (f"FS = {fs:.2f}; vacía se vuelca con F_h ≥ {r['f_h_limite_n']:.0f} N a "
                      f"{r['altura_mm']:.0f} mm (con la carga útil encima, "
                      f"{r['f_h_limite_con_carga_n']:.0f} N: no se cuenta)"
                      if math.isfinite(fs) else "sin momento desestabilizante"),
        "criterio": "M_estab,d ≥ M_desest,d en la arista más desfavorable",
        "fs": round(fs, 2) if math.isfinite(fs) else None,
        "norma": NORMA,
    }
    det = (f"Con las fuerzas de trabajo declaradas (F_h {r['f_h']:.0f} N a {h_txt}, borde "
           f"{r['p_b']:.0f} N): FS al vuelco {fs:.2f} en la arista más desfavorable; vacía se "
           f"vuelca a partir de F_h ≈ {r['f_h_limite_n']:.0f} N.")
    if fs < 1.0:
        out = _check(REGLA, "error", det, "Ensancha la base hacia ese lado, ánclala al piso, baja "
                     "la altura de empuje o agrega peso abajo.", calc=calc)
    else:
        out = _check(REGLA, "ok", det, calc=calc)
    out["hipotesis"] = [
        "La carga útil no estabiliza (EN 1990 A1.2(A): variable favorable × 0): manda la máquina "
        "vacía.",
        "F_h perpendicular a cada arista, hacia fuera; la carga de borde en el punto del contorno "
        "de la máquina que más vuela sobre esa arista.",
    ]
    return out


__all__ = ["NORMA", "REGLA", "evaluar", "regla"]
