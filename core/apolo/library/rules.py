"""Reglas de ingeniería del vertical de transportadores de rodillos.

Funciones puras y testeables: el conocimiento vive aquí, no en el prompt del
agente. Cada comprobación devuelve {regla, estado, detalle, recomendacion?}
con estado "ok" | "aviso" | "error".
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .catalog import CATALOG, category_refs_sorted
from .materials import density, resolve_material, yield_strength, young_modulus
from .structural import beam_udl_deflection_mm, rect_tube_inertia_mm4, shaft_bending_stress_mpa

FRICTION_COEFF = 0.06  # rodadura + cojinetes
EFFICIENCY = 0.85
POWER_MARGIN = 1.3
RAIL_W = 40.0
DEFLECTION_RATIO = 250.0  # flecha admisible del bastidor = L / 250
SHAFT_SAFETY = 2.0        # factor de seguridad sobre el límite elástico del eje

_HP_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*hp", re.I)
_KW_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*kw", re.I)
_SECTION_RE = re.compile(r"(\d+)\s*[x×]\s*(\d+)\s*[x×]\s*(\d+)")  # 80x40x3
_DIAM_RE = re.compile(r"[øØ⌀]\s*(\d+(?:[.,]\d+)?)", re.I)


def _f(x) -> float | None:
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _parse_power_kw(name: str) -> float | None:
    """Potencia del motor (kW) parseada del nombre: '1.5HP' → 1.12 kW, '1.1 kW' → 1.1."""
    m = _KW_RE.search(name or "")
    if m:
        return _f(m.group(1))
    m = _HP_RE.search(name or "")
    if m:
        hp = _f(m.group(1))
        return round(hp * 0.7457, 3) if hp else None
    return None


def _parse_wall(name: str) -> float | None:
    """Espesor de pared (mm) de una sección de tubo '80x40x3' → 3."""
    m = _SECTION_RE.search(name or "")
    return _f(m.group(3)) if m else None


def _parse_diam(name: str) -> float | None:
    """Diámetro (mm) de un 'Ø35'/'Ø 35' en el nombre."""
    m = _DIAM_RE.search(name or "")
    return _f(m.group(1)) if m else None


def _vol_safe(f) -> float:
    try:
        return float(f.shape.volume)
    except Exception:
        return 0.0


def _check(regla: str, estado: str, detalle: str, recomendacion: str | None = None) -> dict:
    out = {"regla": regla, "estado": estado, "detalle": detalle}
    if recomendacion:
        out["recomendacion"] = recomendacion
    return out


def required_force_n(carga_kg: float, largo_mm: float, largo_paquete_mm: float) -> float:
    """Fuerza de arrastre (N) para mover los paquetes simultáneos (rodadura+cojinetes)."""
    n_paquetes = max(1, math.floor(largo_mm / (largo_paquete_mm * 2.0)))
    return n_paquetes * carga_kg * 9.81 * FRICTION_COEFF


def required_power_kw(carga_kg: float, largo_mm: float, largo_paquete_mm: float, velocidad_m_s: float) -> float:
    """Potencia mínima recomendada (con margen) para mover los paquetes simultáneos."""
    force_n = required_force_n(carga_kg, largo_mm, largo_paquete_mm)
    return force_n * velocidad_m_s / EFFICIENCY / 1000.0 * POWER_MARGIN


def band_speed_m_s(rpm_salida: float, tambor_d_mm: float) -> float:
    """Velocidad lineal de banda (m/s) = rpm · π · Ø_tambor / 60000."""
    return rpm_salida * math.pi * tambor_d_mm / 60000.0


def recommend_motor(carga_kg: float, largo_mm: float, largo_paquete_mm: float, velocidad_m_s: float) -> str:
    p_req = required_power_kw(carga_kg, largo_mm, largo_paquete_mm, velocidad_m_s)
    refs = category_refs_sorted("motorreductores", "potencia_kW")
    for ref in refs:
        if CATALOG[ref].specs["potencia_kW"] >= p_req:
            return ref
    return refs[-1]


def recommend_roller(carga_kg: float, largo_paquete_mm: float, paso_mm: float) -> str:
    apoyo = max(1, math.floor(largo_paquete_mm / paso_mm))
    carga_por_rodillo = carga_kg / apoyo
    refs = category_refs_sorted("rodillos", "capacidad_kg")
    for ref in refs:
        if CATALOG[ref].specs["capacidad_kg"] >= carga_por_rodillo:
            return ref
    return refs[-1]


def _name(f) -> str:
    return (getattr(f, "name", "") or "").lower()


def _frame_from_scene(scene: dict, variables: dict | None) -> dict | None:
    """Extrae el bastidor para el chequeo de flecha: sección del larguero (ancho×alto,
    pared), material, VANO máximo entre patas, longitud total y peso transportado
    (estructura+banda+mesa, sin la carga del producto)."""
    v = variables or {}
    largueros = [f for f in scene.values()
                 if getattr(f, "visible", True)
                 and ("larguero" in _name(f) or "perfil" in _name(f))]
    if not largueros:
        return None
    f0 = largueros[0]
    b = _bbox_safe(f0)
    if b is None:
        return None
    width = round(b.max.Y - b.min.Y, 1)   # ancho horizontal de la sección
    depth = round(b.max.Z - b.min.Z, 1)   # alto (dirección de la carga vertical)
    length = round(b.max.X - b.min.X, 1)  # longitud de la viga
    wall = _f(v.get("esp_larg")) or _parse_wall(getattr(f0, "name", "")) or 3.0
    material = resolve_material(f0)
    # vano: mayor hueco entre patas (apoyos); sin ≥2 patas → la longitud completa
    patas = [f for f in scene.values()
             if getattr(f, "visible", True) and "pata" in _name(f)]
    xs = sorted({round((bb.min.X + bb.max.X) / 2.0, 1)
                 for f in patas if (bb := _bbox_safe(f))})
    span = max((b2 - a for a, b2 in zip(xs, xs[1:])), default=0.0)
    if span <= 0:
        span = length
    # peso que carga el bastidor (estructura+banda+mesa); el producto se suma en el chequeo
    carried = 0.0
    for f in scene.values():
        if not getattr(f, "visible", True):
            continue
        if any(w in _name(f) for w in ("banda", "mesa", "cinta", "faja", "larguero",
                                       "travesa", "perfil", "repisa")):
            carried += _vol_safe(f) * density(resolve_material(f))
    return {
        "span_mm": round(span, 1),
        "length_mm": length,
        "width": width,
        "depth": depth,
        "wall": round(float(wall), 1),
        "material": material,
        "carried_kg": round(carried, 2),
        "n_largueros": len(largueros),
    }


def _enrich_conveyor(base: dict, scene: dict, variables: dict | None) -> dict:
    """Rellena los campos de ingeniería que faltan (tambor, rpm, motor a-medida, eje,
    bastidor) con las VARIABLES del proyecto y los nombres — para validar una faja hecha
    a mano cuyos datos no viven en componentes de catálogo. Solo rellena lo que falta."""
    v = variables or {}
    if not base.get("tambor_d"):
        td = _f(v.get("diam_tambor"))
        if td is None:
            cils = [f for f in scene.values()
                    if getattr(f, "visible", True)
                    and any(w in _name(f) for w in ("rodillo", "tambor", "polea"))]
            ds = [min(bb.max.X - bb.min.X, bb.max.Z - bb.min.Z)
                  for f in cils if (bb := _bbox_safe(f))]
            td = round(max(ds), 1) if ds else None
        base["tambor_d"] = td
    if not base.get("rpm_motor"):
        rpm = _f(v.get("rpm_salida"))
        if rpm is None:
            rm, rr = _f(v.get("rpm_motor")), _f(v.get("ratio_red"))
            rpm = rm / rr if (rm and rr) else None
        base["rpm_motor"] = rpm
    if base.get("motor", "ninguno") == "ninguno":
        cands = [f for f in scene.values()
                 if getattr(f, "visible", True)
                 and any(w in _name(f) for w in ("motor", "reductor", "motorreductor"))]
        if cands:
            base["motor"] = "documento"
            # de todos los candidatos (motor + reductor), el de mayor potencia LEGIBLE en
            # el nombre — así el "Motor 1.5HP" gana al "Reductor 1:30" (que no la lleva)
            kw = max((_parse_power_kw(getattr(f, "name", "")) or 0.0 for f in cands), default=0.0)
            if kw > 0:
                base["motor_kW"] = kw
                if not base.get("torque_Nm") and base.get("rpm_motor"):
                    omega = base["rpm_motor"] * 2.0 * math.pi / 60.0
                    if omega > 0:
                        base["torque_Nm"] = round(kw * 1000.0 * EFFICIENCY / omega, 1)
    if not base.get("eje_d"):
        ed = _f(v.get("diam_eje"))
        if ed is None:
            ejef = next((f for f in scene.values()
                         if getattr(f, "visible", True) and "eje" in _name(f)), None)
            ed = _parse_diam(getattr(ejef, "name", "")) if ejef is not None else None
        base["eje_d"] = ed
    if base.get("frame") is None:
        base["frame"] = _frame_from_scene(scene, v)
    return base


def detect_conveyor(scene: dict, variables: dict | None = None) -> dict | None:
    """Infiere los parámetros de una faja HECHA A MANO a partir de sus piezas
    (no del super-comando create_conveyor). Devuelve el mismo dict que consume
    conveyor_engineering_check (+ tipo/tambor_d/rpm_motor/torque_Nm/n_rodillos/frame),
    o None si la escena no parece una faja. `variables` (las del proyecto) enriquece
    la detección (Ø tambor, rpm, motor a-medida, eje, bastidor para la flecha).

    Patrón: ≥1 motorreductor de catálogo Y ≥1 perfil Y (≥1 rodillo de catálogo O
    ≥1 tambor = cilindro sin componente cuyo nombre contiene 'tambor')."""
    motors: list = []
    rollers: list = []
    perfiles: list = []
    tambores: list = []
    for feat in scene.values():
        if not getattr(feat, "visible", True):
            continue
        ref = getattr(feat, "component", None)
        comp = CATALOG.get(ref) if ref else None
        if comp is not None:
            if comp.category == "motorreductores":
                motors.append((feat, ref))
            elif comp.category == "rodillos":
                rollers.append((feat, ref))
            elif comp.category == "perfiles":
                perfiles.append(feat)
        elif "tambor" in (getattr(feat, "name", "") or "").lower():
            tambores.append(feat)

    if not motors or not perfiles or (not rollers and not tambores):
        return _detect_by_name(scene, variables)

    def _bb(f):
        return f.shape.bounding_box()

    def _cx(f):
        b = _bb(f)
        return (b.min.X + b.max.X) / 2.0

    ys = [(_bb(f).min.Y + _bb(f).max.Y) / 2.0 for f in perfiles]
    ancho = round(max(ys) - min(ys), 1) if len(ys) >= 2 else 600.0

    supports = [f for f, _ in rollers] + tambores
    xs = [_cx(f) for f in supports]
    largo = round(max(xs) - min(xs), 1) if len(xs) >= 2 else 2000.0
    altura = round(max((_bb(f).max.Z for f in supports), default=750.0), 1)

    paso = None
    rx = sorted(_cx(f) for f, _ in rollers)
    gaps = [round(b - a, 1) for a, b in zip(rx, rx[1:]) if b - a > 1.0]
    if gaps:
        paso = round(sum(gaps) / len(gaps), 1)

    tambor_d = None
    if tambores:
        ds = [min(_bb(f).max.X - _bb(f).min.X, _bb(f).max.Z - _bb(f).min.Z) for f in tambores]
        tambor_d = round(max(ds), 1)

    motor_ref = motors[0][1]
    motor_specs = CATALOG[motor_ref].specs
    rodillo_ref = Counter(r for _, r in rollers).most_common(1)[0][0] if rollers else "RODILLO-50"

    return _enrich_conveyor({
        "tipo": "banda" if tambores else "rodillos",
        "largo": largo,
        "ancho": ancho,
        "altura": altura,
        "paso": paso,
        "rodillo": rodillo_ref,
        "motor": motor_ref,
        "tambor_d": tambor_d,
        "rpm_motor": motor_specs.get("rpm_salida"),
        "torque_Nm": motor_specs.get("torque_Nm"),
        "n_rodillos": len(rollers),
    }, scene, variables)


def _bbox_safe(f):
    try:
        return f.shape.bounding_box()
    except Exception:
        return None


def _detect_by_name(scene: dict, variables: dict | None = None) -> dict | None:
    """Respaldo: infiere una faja hecha 100% con primitivas a partir de los NOMBRES
    de las piezas (sin componentes de catálogo). Patrón mínimo: una banda o un
    tambor + alguna estructura (larguero/perfil/bastidor). `variables` enriquece
    motor/tambor/rpm/eje/bastidor."""
    def has(*words):
        return [
            f for f in scene.values()
            if getattr(f, "visible", True)
            and any(w in (getattr(f, "name", "") or "").lower() for w in words)
        ]
    banda = has("banda", "faja", "cinta")
    tambores = has("tambor")
    rodillos = has("rodillo")
    estructura = has("larguero", "bastidor", "perfil", "chasis", "estructura")
    if not (banda or tambores) or not (estructura or tambores):
        return None
    soporte = tambores or rodillos or banda
    grupo = [f for f in (banda + tambores + rodillos + estructura) if _bbox_safe(f)]
    bbs = [_bbox_safe(f) for f in grupo]
    if not bbs:
        return None
    largo = round(max(b.max.X for b in bbs) - min(b.min.X for b in bbs), 1)
    sb = [b for f in (banda or soporte) if (b := _bbox_safe(f))]
    ancho = round(max((b.max.Y - b.min.Y for b in sb), default=600.0), 1)
    altura = round(max((b.max.Z for f in soporte if (b := _bbox_safe(f))), default=750.0), 1)
    tambor_d = None
    if tambores:
        ds = [min(b.max.X - b.min.X, b.max.Z - b.min.Z)
              for f in tambores if (b := _bbox_safe(f))]
        tambor_d = round(max(ds), 1) if ds else None
    return _enrich_conveyor({
        "tipo": "banda" if (banda or tambores) else "rodillos",
        "largo": largo,
        "ancho": ancho,
        "altura": altura,
        "paso": None,
        "rodillo": "RODILLO-50",
        "motor": "ninguno",
        "tambor_d": tambor_d,
        "rpm_motor": None,
        "torque_Nm": None,
        "n_rodillos": len(rodillos),
    }, scene, variables)


def infer_from_solids(scene: dict, solid_ids: list[str]) -> dict | None:
    """Infiere los parámetros de la faja a partir de un grupo EXPLÍCITO de sólidos
    (marcados por el usuario con conveyor_solid_ids). Toma el bbox del conjunto."""
    feats = [scene[s] for s in (solid_ids or []) if s in scene]
    bbs = [b for f in feats if (b := _bbox_safe(f))]
    if not bbs:
        return None
    largo = round(max(b.max.X for b in bbs) - min(b.min.X for b in bbs), 1)
    ancho = round(max(b.max.Y for b in bbs) - min(b.min.Y for b in bbs), 1)
    altura = round(max(b.max.Z for b in bbs), 1)
    tambores = [f for f in feats if "tambor" in (getattr(f, "name", "") or "").lower()]
    rodillos = [f for f in feats if "rodillo" in (getattr(f, "name", "") or "").lower()]
    tambor_d = None
    if tambores:
        ds = [min(b.max.X - b.min.X, b.max.Z - b.min.Z)
              for f in tambores if (b := _bbox_safe(f))]
        tambor_d = round(max(ds), 1) if ds else None
    return {
        "tipo": "banda" if tambores else "rodillos",
        "largo": largo,
        "ancho": ancho,
        "altura": altura,
        "paso": None,
        "rodillo": "RODILLO-50",
        "motor": "ninguno",
        "tambor_d": tambor_d,
        "rpm_motor": None,
        "torque_Nm": None,
        "n_rodillos": len(rodillos),
    }


def conveyor_engineering_check(
    conveyor: dict,
    carga_kg: float,
    largo_paquete_mm: float,
    velocidad_m_s: float,
    ancho_paquete_mm: float | None = None,
) -> list[dict]:
    """Valida un transportador (rodillos o banda) contra el paquete. Acepta el dict
    de create_conveyor o el inferido por detect_conveyor (con tipo/tambor_d/rpm/par)."""
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

    # 0 · velocidad de banda (faja con tambor motorizado)
    if v_real is not None:
        det = (f"El accionamiento ({rpm_motor:g} rpm × Ø{tambor_d:g}) da "
               f"{v_real:.3f} m/s ({v_real * 60:.1f} m/min).")
        if velocidad_m_s and velocidad_m_s > 0 and v_real < 0.9 * velocidad_m_s:
            checks.append(_check(
                "velocidad de banda", "aviso",
                det + f" Por debajo del objetivo {velocidad_m_s:g} m/s ({velocidad_m_s * 60:.1f} m/min).",
                "Usa un tambor de mayor Ø o un motorreductor de más rpm.",
            ))
        else:
            checks.append(_check("velocidad de banda", "ok", det))

    # 1 · apoyo del paquete
    if tipo == "banda":
        checks.append(_check(
            "apoyo del paquete", "ok",
            "Soporte continuo por la banda/mesa (no aplica el paso de rodillos).",
        ))
        support_count = max(1, int(conveyor.get("n_rodillos") or 2))
    elif paso > 0:
        apoyo = math.floor(largo_paquete_mm / paso)
        support_count = max(1, apoyo)
        if apoyo >= 3:
            checks.append(_check("apoyo del paquete", "ok", f"El paquete apoya en {apoyo} rodillos (mínimo 3)."))
        elif apoyo == 2:
            checks.append(_check(
                "apoyo del paquete", "aviso",
                f"El paquete solo apoya en 2 rodillos (paso {paso:g} mm).",
                f"Reduce el paso a ≤ {largo_paquete_mm / 3:.0f} mm para 3 apoyos.",
            ))
        else:
            checks.append(_check(
                "apoyo del paquete", "error",
                f"Con paso {paso:g} mm el paquete de {largo_paquete_mm:g} mm puede caer entre rodillos.",
                f"Usa un paso ≤ {largo_paquete_mm / 3:.0f} mm.",
            ))
    else:
        support_count = 1

    # 2 · capacidad del rodillo
    carga_por_rodillo = carga_kg / max(1, support_count)
    capacidad = float(rodillo.specs["capacidad_kg"])
    if carga_por_rodillo <= capacidad:
        checks.append(_check(
            "capacidad de rodillo", "ok",
            f"{carga_por_rodillo:.1f} kg/rodillo ≤ {capacidad:g} kg ({rodillo_ref}).",
        ))
    else:
        sugerido = recommend_roller(carga_kg, largo_paquete_mm, paso or largo_paquete_mm / 3.0)
        checks.append(_check(
            "capacidad de rodillo", "error",
            f"{carga_por_rodillo:.1f} kg/rodillo supera los {capacidad:g} kg del {rodillo_ref}.",
            f"Usa {sugerido} o añade más rodillos.",
        ))

    # 3 · ancho útil
    if ancho_paquete_mm is not None:
        ancho_util = ancho - 2 * RAIL_W - 4
        if ancho_util >= ancho_paquete_mm + 40:
            checks.append(_check("ancho útil", "ok", f"{ancho_util:.0f} mm útiles para paquete de {ancho_paquete_mm:g} mm."))
        elif ancho_util >= ancho_paquete_mm:
            checks.append(_check(
                "ancho útil", "aviso",
                f"Holgura justa: {ancho_util - ancho_paquete_mm:.0f} mm.",
                "Deja ≥ 40 mm de holgura total o añade guías laterales.",
            ))
        else:
            checks.append(_check(
                "ancho útil", "error",
                f"El paquete de {ancho_paquete_mm:g} mm no cabe en {ancho_util:.0f} mm útiles.",
                f"Aumenta el ancho total a ≥ {ancho_paquete_mm + 2 * RAIL_W + 44:.0f} mm.",
            ))

    # 4 · motorización (catálogo, o motor a-medida del documento con potencia parseada)
    p_req = required_power_kw(carga_kg, largo, largo_paquete_mm, v_eff)
    sugerido = recommend_motor(carga_kg, largo, largo_paquete_mm, v_eff)
    p_motor = conveyor.get("motor_kW")
    if p_motor is None and motor_ref not in ("ninguno", "documento") and motor_ref in CATALOG:
        p_motor = CATALOG[motor_ref].specs.get("potencia_kW")
    motor_label = "El motor del documento" if motor_ref == "documento" else motor_ref
    if p_motor is not None:
        p_motor = float(p_motor)
        if p_motor >= p_req:
            checks.append(_check(
                "motorización", "ok",
                f"{motor_label} ({p_motor:g} kW) ≥ {p_req:.2f} kW requeridos (margen {POWER_MARGIN}x incluido).",
            ))
        else:
            checks.append(_check(
                "motorización", "error",
                f"{motor_label} ({p_motor:g} kW) insuficiente: se requieren {p_req:.2f} kW.",
                f"Usa {sugerido}.",
            ))
    elif motor_ref == "documento":
        checks.append(_check(
            "motorización", "aviso",
            f"Motor presente pero sin potencia legible en el nombre; para {v_eff:g} m/s se necesitan ≥ {p_req:.2f} kW.",
            "Indica la potencia en el nombre del motor (p. ej. '1.5HP' o '1.1 kW').",
        ))
    elif v_eff > 0:
        checks.append(_check(
            "motorización", "aviso",
            f"Transportador sin motor; para {v_eff:g} m/s se necesitan ≥ {p_req:.2f} kW.",
            f"Añade {sugerido} ({CATALOG[sugerido].specs['potencia_kW']} kW).",
        ))
    else:
        checks.append(_check("motorización", "ok", "Transportador de gravedad (sin motor)."))

    # 5 · par del motor en el tambor (faja con tambor motorizado)
    if torque_nm and tambor_d:
        par_req = required_force_n(carga_kg, largo, largo_paquete_mm) * (tambor_d / 2.0 / 1000.0)
        if torque_nm >= par_req:
            checks.append(_check(
                "par del motor", "ok",
                f"Par disponible {torque_nm:g} N·m ≥ {par_req:.1f} N·m requeridos en el tambor Ø{tambor_d:g}.",
            ))
        else:
            checks.append(_check(
                "par del motor", "error",
                f"Par del motor {torque_nm:g} N·m < {par_req:.1f} N·m requeridos en el tambor Ø{tambor_d:g}.",
                "Usa un motorreductor de mayor par o un tambor de menor Ø.",
            ))

    # 6 · velocidad ↔ rodillo (informativo)
    if v_eff > 0:
        d = float(rodillo.specs["diametro_mm"])
        rpm_req = v_eff * 60000.0 / (math.pi * d)
        checks.append(_check(
            "velocidad", "ok",
            f"{v_eff:g} m/s requiere {rpm_req:.0f} rpm en rodillo Ø{d:g} (ajustable con la transmisión).",
        ))

    # 7 · geometría (altura de trabajo)
    if altura:
        det = f"Altura de trabajo {float(altura):.0f} mm; largo {largo:.0f} mm."
        if 500 <= float(altura) <= 1100:
            checks.append(_check("geometría", "ok", det))
        else:
            checks.append(_check("geometría", "aviso", det + " Fuera del rango ergonómico 500–1100 mm."))

    # 8 · flecha del bastidor (larguero = viga simplemente apoyada entre patas, carga repartida)
    frame = conveyor.get("frame")
    if frame and frame.get("span_mm"):
        span = float(frame["span_mm"])
        length = float(frame.get("length_mm") or span)
        n_larg = max(1, int(frame.get("n_largueros") or 2))
        material = frame.get("material") or "acero"
        e_mpa = young_modulus(material)
        inertia = rect_tube_inertia_mm4(frame["width"], frame["depth"], frame["wall"])
        total_kg = float(frame.get("carried_kg") or 0.0) + carga_kg
        q = total_kg * 9.81 / n_larg / max(length, 1.0)  # N/mm por larguero
        defl = beam_udl_deflection_mm(q, span, e_mpa, inertia)
        allow = span / DEFLECTION_RATIO
        det = (f"Flecha ≈ {defl:.2f} mm en un vano de {span:.0f} mm "
               f"(admisible L/{DEFLECTION_RATIO:.0f} = {allow:.2f} mm; {material}, sección "
               f"{frame['width']:.0f}×{frame['depth']:.0f}×{frame['wall']:.0f}, {total_kg:.0f} kg sobre {n_larg} larguero(s)).")
        if defl <= allow:
            checks.append(_check("flecha del bastidor", "ok", det))
        elif defl <= 2 * allow:
            checks.append(_check(
                "flecha del bastidor", "aviso", det,
                "Acerca las patas (menor vano), usa un larguero de mayor canto o añade apoyos.",
            ))
        else:
            checks.append(_check(
                "flecha del bastidor", "error", det,
                "Vano excesivo: añade patas intermedias o un perfil de mayor inercia.",
            ))

    # 9 · flexión del eje del tambor motorizado (estimación: carga radial ≈ 2× fuerza de arrastre)
    eje_d = conveyor.get("eje_d")
    if eje_d and tambor_d:
        f_rad = 2.0 * required_force_n(carga_kg, largo, largo_paquete_mm)
        span_eje = float(ancho)  # apoyo entre rodamientos ≈ ancho de banda
        sigma = shaft_bending_stress_mpa(f_rad, span_eje, float(eje_d))
        material = (frame or {}).get("material") or "acero"
        allow = yield_strength(material) / SHAFT_SAFETY
        det = (f"Eje Ø{float(eje_d):.0f} a flexión ≈ {sigma:.0f} MPa entre apoyos de {span_eje:.0f} mm "
               f"(admisible σy/{SHAFT_SAFETY:.0f} = {allow:.0f} MPa, {material}). Estimación.")
        if sigma <= allow:
            checks.append(_check("flexión del eje", "ok", det))
        else:
            checks.append(_check(
                "flexión del eje", "error", det,
                "Usa un eje de mayor Ø o acerca los rodamientos (menor luz entre apoyos).",
            ))

    return checks
