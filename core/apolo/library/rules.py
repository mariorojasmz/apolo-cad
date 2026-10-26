"""Reglas de ingeniería del vertical de transportadores de rodillos.

Funciones puras y testeables: el conocimiento vive aquí, no en el prompt del
agente. Cada comprobación devuelve {regla, estado, detalle, recomendacion?}
con estado "ok" | "aviso" | "error".

Las reglas leen TODAS las piezas de la escena, también las ocultas: la visibilidad es
estado de VISTA (`Document.hidden`), no de diseño — ocultar la banda y el tambor para mirar
dentro no saca la faja del cálculo. Ningún filtro por `visible` en este módulo.

Módulos (plan partir-nucleo-congelado-ii, F3): `rules_comun` (constantes, regex, `_check`,
parseo de nombres), `rules_calculo` (potencia, velocidad, recomendación de catálogo),
`rules_deteccion` + `rules_enriquecer` (detectar la faja a mano) y los bloques de
`conveyor_engineering_check` en `rules_faja_*` con su estado en `ContextoFaja`. Aquí queda el
orquestador y la ruta vieja: re-exporta por IDENTIDAD todo nombre de antes
(`tests/test_rutas_viejas.py`). Una regla nueva va a su `rules_faja_*`, no aquí.
"""

from __future__ import annotations

from .catalog import CATALOG
from .rules_calculo import (  # noqa: F401
    required_force_n, required_power_kw, band_speed_m_s, recommend_motor_kw, recommend_motor,
    recommend_roller,
)
from .rules_comun import (  # noqa: F401
    FRICTION_COEFF, EFFICIENCY, POWER_MARGIN, RAIL_W, DEFLECTION_RATIO, SHAFT_SAFETY, _HP_RE,
    _KW_RE, _SECTION_RE, _DIAM_RE, _LEG_RE, _LARG_RE, _EJE_RE, _BANDA_RE, _f, _parse_power_kw,
    _parse_wall, _parse_diam, _vol_safe, _check, _name, _bbox_safe,
)
from .rules_deteccion import detect_conveyor, _detect_by_name, infer_from_solids  # noqa: F401
from .rules_enriquecer import _frame_from_scene, _enrich_conveyor  # noqa: F401
from .rules_faja_contexto import ContextoFaja
from .rules_faja_estructura import verificar_flecha_del_bastidor, verificar_flexion_del_eje
from .rules_faja_motor import verificar_arrastre, verificar_motorizacion
from .rules_faja_tambor import verificar_adherencia_del_tambor, verificar_par_del_motor
from .rules_faja_transporte import (
    verificar_ancho_util, verificar_apoyo_del_paquete, verificar_capacidad_de_rodillo,
    verificar_geometria, verificar_velocidad_de_banda, verificar_velocidad_del_rodillo,
)


def conveyor_engineering_check(conveyor: dict, carga_kg: float, largo_paquete_mm: float,
                               velocidad_m_s: float, ancho_paquete_mm: float | None = None) -> list[dict]:
    """Valida un transportador (rodillos o banda) contra el paquete. Acepta el dict de
    create_conveyor, el inferido por detect_conveyor (con tipo/tambor_d/rpm/par) o el de un
    create_roller_conveyor (`plantilla`: sus reglas puras, `rodillos_cadena_reglas.py`)."""
    if conveyor.get("plantilla") == "create_roller_conveyor":
        from .rodillos_cadena_reglas import reglas_rodillos_cadena as reglas
        return reglas(conveyor, carga_kg, largo_paquete_mm, velocidad_m_s, ancho_paquete_mm)
    if conveyor.get("a_mano"):  # rodillos de tubo con eje y rodamientos: capacidad y motor medidos
        from .rodillos_a_mano_reglas import reglas_a_mano
        return reglas_a_mano(conveyor, carga_kg, largo_paquete_mm, velocidad_m_s, ancho_paquete_mm)
    checks: list[dict] = []
    largo = float(conveyor.get("largo") or 2000)
    ancho = float(conveyor.get("ancho") or 600)
    paso = float(conveyor.get("paso") or 0)
    rodillo_ref = conveyor.get("rodillo", "RODILLO-50")
    motor_ref = conveyor.get("motor", "ninguno")
    tipo = conveyor.get("tipo", "rodillos")
    tambor_d = conveyor.get("tambor_d")
    rpm_motor = conveyor.get("rpm_motor")
    torque_nm = conveyor.get("torque_Nm")
    altura = conveyor.get("altura")
    rodillo = CATALOG[rodillo_ref]

    # velocidad real del accionamiento (tambor motorizado) y velocidad efectiva
    v_real = band_speed_m_s(rpm_motor, tambor_d) if (tambor_d and rpm_motor) else None
    v_eff = velocidad_m_s if velocidad_m_s and velocidad_m_s > 0 else (v_real or 0.0)

    # un bloque por verificación, en el orden de siempre (rules_faja_*.py, plan
    # partir-nucleo-congelado-ii D4): lo que un bloque produce para otro vuelve a `ctx`
    ctx = ContextoFaja(
        conveyor=conveyor, carga_kg=carga_kg, largo_paquete_mm=largo_paquete_mm,
        velocidad_m_s=velocidad_m_s, ancho_paquete_mm=ancho_paquete_mm, checks=checks,
        largo=largo, ancho=ancho, paso=paso, rodillo_ref=rodillo_ref, motor_ref=motor_ref,
        tipo=tipo, tambor_d=tambor_d, rpm_motor=rpm_motor, torque_nm=torque_nm, altura=altura,
        rodillo=rodillo, v_real=v_real, v_eff=v_eff,
    )
    verificar_velocidad_de_banda(ctx)
    ctx.support_count = verificar_apoyo_del_paquete(ctx)
    verificar_capacidad_de_rodillo(ctx)
    verificar_ancho_util(ctx)
    ctx.soporte, ctx.metodo_norma, ctx.pull_n, ctx.p_req = verificar_arrastre(ctx)
    verificar_motorizacion(ctx)
    verificar_par_del_motor(ctx)
    verificar_adherencia_del_tambor(ctx)
    verificar_velocidad_del_rodillo(ctx)
    verificar_geometria(ctx)
    ctx.frame = verificar_flecha_del_bastidor(ctx)
    verificar_flexion_del_eje(ctx)

    return checks
