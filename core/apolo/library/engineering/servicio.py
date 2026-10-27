"""FACTOR DE SERVICIO de un accionamiento con lo DECLARADO (F3c de puerta-sin-sobrediseno, D10).
Puro.

Antes sólo lo calculaban las reglas del transportador: en un agitador, una mezcladora o un
elevador el ítem quedaba SIN_EVALUAR aunque el motorreductor es de catálogo y la máquina declara
su carga. Aquí:

- **Lo que pide la máquina** (requisitos, `library/requisitos.py`): `potencia_absorbida_kw` (lo
  que absorbe en el eje de salida del reductor, p. ej. Np·ρ·N³·D⁵ de una hélice) o `par_salida_nm`
  (el par en ese eje a plena carga). Nunca `carga_kg` (el producto: no es lo que carga el motor de
  un agitador) ni el `atasco` de un escenario (es una FALLA provocada para verificar que la
  protección dispare: dimensionar contra él pediría un motor que nunca se protege).
- **Lo que da el motorreductor** (ficha): su potencia de placa por el rendimiento del reductor
  (sinfín-corona 0,75; helicoidal `EFFICIENCY` 0,85: los de `rules_enriquecer`) o su par de salida
  de catálogo (`torque_Nm`); con par pedido y sin par de catálogo, el par sale de las rpm
  declaradas (`rodamientos_declarados`).
- **FS = lo que da / lo que pide**, contra el FS que pide su SERVICIO: la tabla de clases de
  servicio de AGMA para motor eléctrico (`TABLA_AGMA`, la que reproducen los catálogos de
  reductores; a confirmar con el fabricante del reductor elegido) por tipo de carga
  (`tipo_carga`: uniforme | moderada | pesada) y horas por día (`horas_dia`). Sin servicio
  declarado, 1,25: uniforme y más de 10 h/día, la cifra fija de antes. Nunca menos de 1,0
  (criterio propio, más estricto que la tabla para ≤ 3 h/día: el par nominal de la ficha no se
  excede).
"""

from __future__ import annotations

REGLA = "factor de servicio del accionamiento"
TIPOS_CARGA = ("uniforme", "moderada", "pesada")
#: AGMA, clases de servicio con motor eléctrico: (≤ 3 h/día, ≤ 10 h/día, > 10 h/día).
TABLA_AGMA = {"uniforme": (0.8, 1.0, 1.25), "moderada": (1.0, 1.25, 1.5),
              "pesada": (1.5, 1.75, 2.0)}
FS_SIN_SERVICIO = 1.25
FS_MINIMO = 1.0
ETA_SINFIN = 0.75
NORMA = ("AGMA (factor de servicio por clase de carga y horas/día, motor eléctrico; tabla de los "
         "catálogos de reductores, a confirmar con el fabricante)")


def fs_requerido(tipo_carga: str | None, horas_dia: float | None) -> tuple[float, str]:
    """(FS que pide el servicio, de dónde sale)."""
    if not tipo_carga and not horas_dia:
        return FS_SIN_SERVICIO, ("servicio no declarado (tipo_carga, horas_dia): carga uniforme "
                                 "y más de 10 h/día")
    tipo = tipo_carga if tipo_carga in TABLA_AGMA else "uniforme"
    col = 2 if not horas_dia or horas_dia > 10 else (1 if horas_dia > 3 else 0)
    fs = max(FS_MINIMO, TABLA_AGMA[tipo][col])
    horas = f"{horas_dia:g} h/día" if horas_dia else "horas no declaradas: más de 10 h/día"
    nota = "" if tipo_carga in TABLA_AGMA else " (tipo de carga no declarado: uniforme)"
    piso = " (mínimo 1,0)" if TABLA_AGMA[tipo][col] < FS_MINIMO else ""
    return fs, f"carga {tipo}{nota}, {horas} → {fs:g}{piso}"


def regla_factor_servicio(motor: dict, req: dict, rpm: float | None, fs_req: float,
                          origen_fs: str) -> dict:
    """La regla (formato `rules_comun._check`) de UN motorreductor. `motor` = {fid, nombre, ref,
    potencia_kw, torque_nm?, sinfin}; `req` = los requisitos; `rpm` = las de salida declaradas.
    Sin lo que pide la máquina: aviso sin `calc` (el ítem queda SIN_EVALUAR y dice qué declarar)."""
    p_abs = _num(req.get("potencia_absorbida_kw"))
    t_req = _num(req.get("par_salida_nm"))
    eta = ETA_SINFIN if motor.get("sinfin") else 0.85
    p_kw = _num(motor.get("potencia_kw"))
    base = {"regla": REGLA, "piezas": [motor.get("fid") or motor["nombre"]]}
    if p_kw is None:
        return {**base, "estado": "aviso", "detalle": f"{motor['nombre']}: la ficha no trae su "
                "potencia: el factor de servicio no se puede calcular"}
    if p_abs is not None:
        fs = p_kw * eta / p_abs
        entradas = {"P motor": f"{p_kw:g} kW", "η reductor": f"{eta:g}",
                    "P absorbida": f"{p_abs:g} kW (requisito potencia_absorbida_kw)"}
        formula, sust = "FS = P·η / P_abs", f"{p_kw:g}·{eta:g} / {p_abs:g}"
    elif t_req is not None:
        t_nom = _num(motor.get("torque_nm"))
        de_ficha = t_nom is not None
        if t_nom is None and rpm:
            t_nom = 9550.0 * p_kw * eta / rpm
        if t_nom is None:
            return {**base, "estado": "aviso", "detalle": f"{motor['nombre']}: con el par pedido "
                    "hacen falta las rpm de salida (requisito rpm_salida) o el par de catálogo"}
        fs = t_nom / t_req
        entradas = {"T nominal": f"{t_nom:.1f} N·m" + (" (ficha)" if de_ficha else
                                                       f" (9550·{p_kw:g}·{eta:g}/{rpm:g} rpm)"),
                    "T pedido": f"{t_req:g} N·m (requisito par_salida_nm)"}
        formula, sust = "FS = T_nominal / T_pedido", f"{t_nom:.1f} / {t_req:g}"
    else:
        return {**base, "estado": "aviso", "detalle": (
            f"{motor['nombre']}: la máquina no declara lo que pide al accionamiento: declara "
            "`potencia_absorbida_kw` (lo que absorbe en el eje de salida) o `par_salida_nm` con "
            "set_requirements; el factor de servicio no se inventa")}
    estado = "ok" if fs >= fs_req - 1e-6 else ("aviso" if fs >= 1.0 else "error")
    return {**base, "estado": estado,
            "detalle": f"{motor['nombre']} ({motor.get('ref')}): FS {fs:.2f} (pide {fs_req:g}: "
                       f"{origen_fs})",
            "calc": {"titulo": f"Factor de servicio: {motor['nombre']}", "entradas": entradas,
                     "formula": formula, "sustitucion": sust, "resultado": f"FS = {fs:.2f}",
                     "criterio": f"FS ≥ {fs_req:g} ({origen_fs})", "fs": round(fs, 2),
                     "fs_requerido": fs_req, "norma": NORMA}}


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None
