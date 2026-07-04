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
from .engineering.belt import belt_power_kw, belt_pull_n, belt_startup_torque_nm, estimate_belt_kg
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


def _check(
    regla: str,
    estado: str,
    detalle: str,
    recomendacion: str | None = None,
    *,
    calc: dict | None = None,
) -> dict:
    """Una regla del reporte. `calc` (opcional, Frente A) enriquece la regla con el
    CÁLCULO detrás del veredicto — lo consume la memoria de cálculo:
    {titulo, entradas: {k: "valor unidad"}, formula, sustitucion, resultado,
    criterio, fs: float|None}. Sin `calc`, el formato queda byte-idéntico al histórico."""
    out = {"regla": regla, "estado": estado, "detalle": detalle}
    if recomendacion:
        out["recomendacion"] = recomendacion
    if calc:
        out["calc"] = calc
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


def recommend_motor_kw(p_req: float) -> str:
    """Ref de motorreductor comercial más chico que cubre `p_req` kW."""
    refs = category_refs_sorted("motorreductores", "potencia_kW")
    for ref in refs:
        if CATALOG[ref].specs["potencia_kW"] >= p_req:
            return ref
    return refs[-1]


def recommend_motor(carga_kg: float, largo_mm: float, largo_paquete_mm: float, velocidad_m_s: float) -> str:
    return recommend_motor_kw(required_power_kw(carga_kg, largo_mm, largo_paquete_mm, velocidad_m_s))


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
            # de todos los candidatos (motor + reductor), el de mayor potencia CONOCIDA:
            # specs de catálogo (potencia_kW — un NMRV insertado la lleva) o legible en el
            # nombre — así el "Motor 1.5HP" gana al "Reductor 1:30" (que no la lleva)
            kw, kw_comp = 0.0, None
            for f in cands:
                comp = CATALOG.get(getattr(f, "component", None) or "")
                spec_kw = float((comp.specs or {}).get("potencia_kW") or 0.0) if comp else 0.0
                name_kw = _parse_power_kw(getattr(f, "name", "")) or 0.0
                if max(spec_kw, name_kw) > kw:
                    kw, kw_comp = max(spec_kw, name_kw), comp
            if kw > 0:
                base["motor_kW"] = kw
                if not base.get("torque_Nm") and base.get("rpm_motor"):
                    omega = base["rpm_motor"] * 2.0 * math.pi / 60.0
                    if omega > 0:
                        # un sinfín-corona rinde ~0.7-0.8 (mucho menos que un helicoidal)
                        eff = 0.75 if (kw_comp is not None
                                       and kw_comp.category == "motorreductores_sinfin") else EFFICIENCY
                        base["torque_Nm"] = round(kw * 1000.0 * eff / omega, 1)
    if not base.get("eje_d"):
        ed = _f(v.get("diam_eje"))
        if ed is None:
            ejef = next((f for f in scene.values()
                         if getattr(f, "visible", True) and "eje" in _name(f)), None)
            ed = _parse_diam(getattr(ejef, "name", "")) if ejef is not None else None
        base["eje_d"] = ed
    if not base.get("banda_kg"):
        bandas = [f for f in scene.values()
                  if getattr(f, "visible", True)
                  and any(w in _name(f) for w in ("banda", "cinta", "faja"))]
        kg = sum(_vol_safe(f) * density(resolve_material(f)) for f in bandas)
        if kg > 0:
            base["banda_kg"] = round(kg, 2)
    if base.get("frame") is None:
        base["frame"] = _frame_from_scene(scene, v)
    # --- señales normativas (V5.10): la regla elige el MÉTODO por construcción
    if "soporte" not in base and base.get("tipo") == "banda":
        # cama deslizante (slider bed) si hay mesa/cama visible; si no y hay
        # rodillos portantes → idlers; default honesto del vertical: cama
        tiene_cama = any(
            getattr(f, "visible", True)
            and any(w in _name(f) for w in ("cama", "mesa", "desliz"))
            for f in scene.values()
        )
        base["soporte"] = "cama" if (tiene_cama or not base.get("n_rodillos")) else "rodillos"
    if "tambor_engomado" not in base:
        base["tambor_engomado"] = any(
            getattr(f, "visible", True)
            and "tambor" in _name(f)
            and any(w in _name(f) for w in ("engomado", "lagging", "goma"))
            for f in scene.values()
        )
    if "tiene_tensor" not in base:
        base["tiene_tensor"] = any(
            getattr(f, "visible", True)
            and any(w in _name(f) for w in ("tensor", "trotadora", "take-up", "take up", "templador"))
            for f in scene.values()
        )
    if not base.get("q_ro_kg_m") and base.get("largo"):
        # masa por metro de partes giratorias (rodillos de catálogo, por FICHA)
        kg = 0.0
        for f in scene.values():
            if not getattr(f, "visible", True):
                continue
            comp = CATALOG.get(getattr(f, "component", None) or "")
            if comp is not None and comp.category == "rodillos":
                kg += float(comp.weight or 0.0)
        if kg > 0:
            base["q_ro_kg_m"] = round(kg / (base["largo"] / 1000.0), 3)
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
            if comp.category in ("motorreductores", "motorreductores_sinfin"):
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
        calc_v = {
            "titulo": "Velocidad de banda",
            "entradas": {"rpm de salida": f"{rpm_motor:g} rpm", "Ø tambor": f"{tambor_d:g} mm",
                         "objetivo": f"{velocidad_m_s:g} m/s" if velocidad_m_s else "—"},
            "formula": "v = n·π·Ø / 60000",
            "sustitucion": f"v = {rpm_motor:g}·π·{tambor_d:g} / 60000",
            "resultado": f"v = {v_real:.3f} m/s ({v_real * 60:.1f} m/min)",
            "criterio": (f"v ≥ 0.9 × objetivo = {0.9 * velocidad_m_s:.3f} m/s"
                         if velocidad_m_s else "informativo"),
            "fs": round(v_real / velocidad_m_s, 2) if velocidad_m_s else None,
        }
        det = (f"El accionamiento ({rpm_motor:g} rpm × Ø{tambor_d:g}) da "
               f"{v_real:.3f} m/s ({v_real * 60:.1f} m/min).")
        if velocidad_m_s and velocidad_m_s > 0 and v_real < 0.9 * velocidad_m_s:
            checks.append(_check(
                "velocidad de banda", "aviso",
                det + f" Por debajo del objetivo {velocidad_m_s:g} m/s ({velocidad_m_s * 60:.1f} m/min).",
                "Usa un tambor de mayor Ø o un motorreductor de más rpm.",
                calc=calc_v,
            ))
        else:
            checks.append(_check("velocidad de banda", "ok", det, calc=calc_v))

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
    calc_rod = {
        "titulo": "Capacidad de rodillo",
        "entradas": {"carga por paquete": f"{carga_kg:g} kg", "apoyos": f"{support_count}",
                     "rodillo": f"{rodillo_ref} ({capacidad:g} kg/ud)"},
        "formula": "P = carga / n_apoyos",
        "sustitucion": f"P = {carga_kg:g} / {max(1, support_count)}",
        "resultado": f"P = {carga_por_rodillo:.1f} kg/rodillo",
        "criterio": f"P ≤ {capacidad:g} kg (capacidad de catálogo)",
        "fs": round(capacidad / carga_por_rodillo, 2) if carga_por_rodillo > 0 else None,
    }
    if carga_por_rodillo <= capacidad:
        checks.append(_check(
            "capacidad de rodillo", "ok",
            f"{carga_por_rodillo:.1f} kg/rodillo ≤ {capacidad:g} kg ({rodillo_ref}).",
            calc=calc_rod,
        ))
    else:
        sugerido = recommend_roller(carga_kg, largo_paquete_mm, paso or largo_paquete_mm / 3.0)
        checks.append(_check(
            "capacidad de rodillo", "error",
            f"{carga_por_rodillo:.1f} kg/rodillo supera los {capacidad:g} kg del {rodillo_ref}.",
            f"Usa {sugerido} o añade más rodillos.",
            calc=calc_rod,
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

    # 4 · motorización — una BANDA sobre cama desliza (μ≈0.33, engineering/belt.py),
    # MUY distinto de la rodadura (μ=0.06) del transportador de rodillos.
    n_paq = max(1, math.floor(largo / (largo_paquete_mm * 2.0))) if largo_paquete_mm > 0 else 1
    incline = float(conveyor.get("inclinacion_deg") or 0.0)
    soporte = conveyor.get("soporte", "cama")
    metodo_norma = None  # norma del método de arrastre/potencia elegido (V5.10)
    if tipo == "banda" and soporte == "rodillos":
        # banda sobre RODILLOS (idlers) → método ISO 5048 / DIN 22101
        from .engineering.iso5048 import F_ISO, c_coefficient, effective_tension_n

        banda_kg = float(conveyor.get("banda_kg") or estimate_belt_kg(largo, ancho))
        l_m = largo / 1000.0
        q_g = n_paq * carga_kg / l_m
        q_b = banda_kg / (2.0 * l_m)  # masa de UN tramo por metro (el lazo pesa 2·q_B)
        q_ro = float(conveyor.get("q_ro_kg_m") or 0.0)  # giratorias agregadas (ida+retorno)
        h_m = l_m * math.sin(math.radians(incline))
        cc = c_coefficient(l_m)
        pull_n = effective_tension_n(F_ISO, l_m, q_ro, 0.0, q_b, q_g,
                                     delta_deg=incline, h_m=h_m)
        p_req = belt_power_kw(pull_n, v_eff, EFFICIENCY, POWER_MARGIN)
        metodo_norma = "ISO 5048 / DIN 22101"
        calc_pull = {
            "titulo": "Tensión efectiva (banda sobre rodillos)",
            "entradas": {"q_G carga": f"{q_g:.2f} kg/m", "q_B banda": f"{q_b:.2f} kg/m",
                         "q_RO giratorias": f"{q_ro:.2f} kg/m",
                         "f": f"{F_ISO} (rodadura idlers)",
                         "C(L)": f"{cc:.2f} (L={l_m:g} m"
                                 + ("; <80 m: interpolado, referencial)" if l_m < 80 else ")"),
                         "inclinación": f"{incline:g}°"},
            "formula": "F_U = C(L)·f·L·g·(q_RO + (2·q_B + q_G)·cos δ) + q_G·H·g",
            "sustitucion": (f"F_U = {cc:.2f}·{F_ISO}·{l_m:g}·9.81·({q_ro:.2f} + "
                            f"(2·{q_b:.2f} + {q_g:.2f})·cos {incline:g}°) + elevación"),
            "resultado": f"F_U = {pull_n:.1f} N",
            "criterio": "informativo (alimenta potencia y par)",
            "fs": None,
            "norma": "ISO 5048 / DIN 22101",
        }
        checks.append(_check(
            "arrastre de banda", "ok",
            f"Tensión efectiva {pull_n:.1f} N (banda sobre rodillos, método ISO 5048: "
            f"f={F_ISO}, C(L)={cc:.2f}).",
            calc=calc_pull,
        ))
    elif tipo == "banda":
        banda_kg = float(conveyor.get("banda_kg") or estimate_belt_kg(largo, ancho))
        pull_n = belt_pull_n(n_paq * carga_kg, banda_kg, incline_deg=incline)
        p_req = belt_power_kw(pull_n, v_eff, EFFICIENCY, POWER_MARGIN)
        metodo_norma = "CEMA (unit handling) — slider bed"
        calc_pull = {
            "titulo": "Arrastre de banda sobre cama (método CEMA slider-bed)",
            "entradas": {"carga simultánea": f"{n_paq} paq × {carga_kg:g} kg",
                         "peso de banda": f"{banda_kg:.1f} kg",
                         "μ banda-cama": "0.33 (PVC/acero, CEMA slider bed 0.30–0.35)",
                         "inclinación": f"{incline:g}°"},
            "formula": "F = g·(μ·(m_carga + m_banda) + m_carga·sen θ)",
            "sustitucion": (f"F = 9.81·(0.33·({n_paq * carga_kg:g} + {banda_kg:.1f}) + "
                            f"{n_paq * carga_kg:g}·sen {incline:g}°)"),
            "resultado": f"F = {pull_n:.1f} N",
            "criterio": "informativo (alimenta potencia y par)",
            "fs": None,
            "norma": "CEMA (unit handling) — slider bed, μ = 0.30–0.35",
        }
        checks.append(_check(
            "arrastre de banda", "ok",
            f"Fuerza de arrastre efectiva {pull_n:.1f} N "
            f"(banda sobre cama, μ=0.33, {n_paq} paquete(s) + {banda_kg:.1f} kg de banda).",
            calc=calc_pull,
        ))
    else:
        pull_n = required_force_n(carga_kg, largo, largo_paquete_mm)
        p_req = required_power_kw(carga_kg, largo, largo_paquete_mm, v_eff)
    sugerido = recommend_motor_kw(p_req)
    p_motor = conveyor.get("motor_kW")
    if p_motor is None and motor_ref not in ("ninguno", "documento") and motor_ref in CATALOG:
        p_motor = CATALOG[motor_ref].specs.get("potencia_kW")
    motor_label = "El motor del documento" if motor_ref == "documento" else motor_ref
    if tipo == "banda":
        mu_label = "ISO 5048 f=0.02" if soporte == "rodillos" else "0.33 banda-cama (CEMA)"
    else:
        mu_label = "0.06 rodadura"
    calc_mot = {
        "titulo": "Motorización",
        "entradas": {"arrastre F": f"{pull_n:.1f} N", "velocidad": f"{v_eff:g} m/s",
                     "η": f"{EFFICIENCY}", "margen": f"{POWER_MARGIN}x", "μ": mu_label},
        "formula": "P = F·v / η · margen",
        "sustitucion": f"P = {pull_n:.1f}·{v_eff:g} / {EFFICIENCY} · {POWER_MARGIN}",
        "resultado": f"P requerida = {p_req:.2f} kW",
        "criterio": "P motor ≥ P requerida",
        "fs": round(float(p_motor) / p_req, 2) if (p_motor and p_req > 0) else None,
    }
    if metodo_norma:
        calc_mot["norma"] = metodo_norma
    if p_motor is not None:
        p_motor = float(p_motor)
        if p_motor >= p_req:
            checks.append(_check(
                "motorización", "ok",
                f"{motor_label} ({p_motor:g} kW) ≥ {p_req:.2f} kW requeridos (margen {POWER_MARGIN}x incluido).",
                calc=calc_mot,
            ))
        else:
            checks.append(_check(
                "motorización", "error",
                f"{motor_label} ({p_motor:g} kW) insuficiente: se requieren {p_req:.2f} kW.",
                f"Usa {sugerido}.",
                calc=calc_mot,
            ))
    elif motor_ref == "documento":
        checks.append(_check(
            "motorización", "aviso",
            f"Motor presente pero sin potencia legible en el nombre; para {v_eff:g} m/s se necesitan ≥ {p_req:.2f} kW.",
            "Indica la potencia en el nombre del motor (p. ej. '1.5HP' o '1.1 kW').",
            calc=calc_mot,
        ))
    elif v_eff > 0:
        checks.append(_check(
            "motorización", "aviso",
            f"Transportador sin motor; para {v_eff:g} m/s se necesitan ≥ {p_req:.2f} kW.",
            f"Añade {sugerido} ({CATALOG[sugerido].specs['potencia_kW']} kW).",
            calc=calc_mot,
        ))
    else:
        checks.append(_check("motorización", "ok", "Transportador de gravedad (sin motor)."))

    # 5 · par del motor en el tambor (faja con tambor motorizado)
    if torque_nm and tambor_d:
        par_req = pull_n * (tambor_d / 2.0 / 1000.0)
        calc_par = {
            "titulo": "Par en el tambor motriz",
            "entradas": {"arrastre F": f"{pull_n:.1f} N", "Ø tambor": f"{tambor_d:g} mm",
                         "par disponible": f"{torque_nm:g} N·m"},
            "formula": "T = F·r",
            "sustitucion": f"T = {pull_n:.1f}·{tambor_d / 2.0 / 1000.0:.4f}",
            "resultado": f"T requerido = {par_req:.1f} N·m",
            "criterio": "T motor ≥ T requerido",
            "fs": round(float(torque_nm) / par_req, 2) if par_req > 0 else None,
        }
        if torque_nm >= par_req:
            checks.append(_check(
                "par del motor", "ok",
                f"Par disponible {torque_nm:g} N·m ≥ {par_req:.1f} N·m requeridos en el tambor Ø{tambor_d:g}.",
                calc=calc_par,
            ))
        else:
            checks.append(_check(
                "par del motor", "error",
                f"Par del motor {torque_nm:g} N·m < {par_req:.1f} N·m requeridos en el tambor Ø{tambor_d:g}.",
                "Usa un motorreductor de mayor par o un tambor de menor Ø.",
                calc=calc_par,
            ))
        # 5b · par de ARRANQUE (solo banda: vencer fricción estática + inercia)
        if tipo == "banda":
            par_arr = belt_startup_torque_nm(pull_n, tambor_d)
            calc_arr = {
                "titulo": "Par de arranque",
                "entradas": {"T régimen": f"{par_req:.1f} N·m", "factor de arranque": "1.6",
                             "par disponible": f"{torque_nm:g} N·m"},
                "formula": "T_arr = F·r · 1.6",
                "sustitucion": f"T_arr = {par_req:.1f} · 1.6",
                "resultado": f"T_arr = {par_arr:.1f} N·m",
                "criterio": "T motor ≥ T_arr",
                "fs": round(float(torque_nm) / par_arr, 2) if par_arr > 0 else None,
                "norma": "factor 1.6 — práctica industrial 1.5–2.0, coherente con "
                         "DIN 22101 (arranque)",
            }
            if torque_nm >= par_arr:
                checks.append(_check(
                    "par de arranque", "ok",
                    f"Par disponible {torque_nm:g} N·m ≥ {par_arr:.1f} N·m de arranque (factor 1.6).",
                    calc=calc_arr,
                ))
            else:
                checks.append(_check(
                    "par de arranque", "aviso",
                    f"Par {torque_nm:g} N·m < {par_arr:.1f} N·m de arranque (factor 1.6): "
                    "puede costarle arrancar a plena carga.",
                    "Sube un tamaño de motorreductor o arranca en vacío.",
                    calc=calc_arr,
                ))

    # 5c · adherencia del tambor motriz (Euler-Eytelwein, V5.10): el tambor solo
    # transmite F_U si el ramal flojo lleva tensión T2 ≥ F_U/(e^{μα}−1) — es lo que
    # el TENSOR debe garantizar. El modelo no declara la tensión real del tensor →
    # se reporta la T2 MÍNIMA requerida (honesto, patrón hanging_load); con `t2_n`
    # explícito en el dict se calcula el FS real.
    if tipo == "banda" and tambor_d and pull_n > 0:
        from .engineering.iso5048 import (
            MU_DRUM, eytelwein_fs, eytelwein_ratio, eytelwein_t2_min_n,
        )

        engomado = bool(conveyor.get("tambor_engomado"))
        mu_t = MU_DRUM["engomado"] if engomado else MU_DRUM["liso"]
        alpha = 180.0  # abrace típico con tensor de cola
        t2_min = eytelwein_t2_min_n(pull_n, mu_t, alpha)
        t2_real = conveyor.get("t2_n")
        ratio = eytelwein_ratio(mu_t, alpha)
        calc_eyt = {
            "titulo": "Adherencia del tambor motriz (Euler-Eytelwein)",
            "entradas": {"F_U (arrastre)": f"{pull_n:.1f} N",
                         "μ tambor": f"{mu_t:g} ({'engomado' if engomado else 'acero liso'})",
                         "α abrace": f"{alpha:g}°",
                         "e^(μα)": f"{ratio:.2f}"},
            "formula": "T2_min = F_U / (e^(μα) − 1)",
            "sustitucion": f"T2_min = {pull_n:.1f} / ({ratio:.2f} − 1)",
            "resultado": f"T2_min = {t2_min:.1f} N",
            "criterio": "el tensor debe garantizar T2 ≥ T2_min (si no, la banda patina)",
            "fs": (round(eytelwein_fs(pull_n + float(t2_real), float(t2_real), mu_t, alpha), 2)
                   if t2_real else None),
            "norma": "Euler-Eytelwein (ISO 5048 · DIN 22101 · CEMA)",
        }
        if conveyor.get("tiene_tensor"):
            checks.append(_check(
                "adherencia del tambor motriz", "ok",
                f"Tambor {'engomado' if engomado else 'liso'} (μ={mu_t:g}, α={alpha:g}°): "
                f"el tensor debe garantizar T2 ≥ {t2_min:.1f} N para transmitir "
                f"{pull_n:.1f} N sin patinar (hay tensor en el modelo).",
                calc=calc_eyt,
            ))
        else:
            checks.append(_check(
                "adherencia del tambor motriz", "aviso",
                f"Sin tensor detectado: la banda necesita T2 ≥ {t2_min:.1f} N en el ramal "
                f"flojo para no patinar (tambor {'engomado' if engomado else 'liso'}, μ={mu_t:g}).",
                "Añade un tensor (take-up) o verifica la tensión de montaje de la banda.",
                calc=calc_eyt,
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
        calc_fle = {
            "titulo": "Flecha del bastidor",
            "entradas": {"vano L": f"{span:.0f} mm",
                         "sección": f"{frame['width']:.0f}×{frame['depth']:.0f}×{frame['wall']:.0f} mm",
                         "E": f"{e_mpa:.0f} MPa ({material})",
                         "I": f"{inertia:.3g} mm⁴",
                         "carga": f"{total_kg:.0f} kg / {n_larg} larguero(s)"},
            "formula": "δ = 5·w·L⁴ / (384·E·I)",
            "sustitucion": f"δ = 5·{q:.3g}·{span:.0f}⁴ / (384·{e_mpa:.0f}·{inertia:.3g})",
            "resultado": f"δ = {defl:.2f} mm",
            "criterio": f"δ ≤ L/{DEFLECTION_RATIO:.0f} = {allow:.2f} mm",
            "fs": round(allow / defl, 2) if defl > 0 else None,
        }
        det = (f"Flecha ≈ {defl:.2f} mm en un vano de {span:.0f} mm "
               f"(admisible L/{DEFLECTION_RATIO:.0f} = {allow:.2f} mm; {material}, sección "
               f"{frame['width']:.0f}×{frame['depth']:.0f}×{frame['wall']:.0f}, {total_kg:.0f} kg sobre {n_larg} larguero(s)).")
        if defl <= allow:
            checks.append(_check("flecha del bastidor", "ok", det, calc=calc_fle))
        elif defl <= 2 * allow:
            checks.append(_check(
                "flecha del bastidor", "aviso", det,
                "Acerca las patas (menor vano), usa un larguero de mayor canto o añade apoyos.",
                calc=calc_fle,
            ))
        else:
            checks.append(_check(
                "flecha del bastidor", "error", det,
                "Vano excesivo: añade patas intermedias o un perfil de mayor inercia.",
                calc=calc_fle,
            ))

    # 9 · flexión del eje del tambor motorizado (estimación: carga radial ≈ 2× fuerza de arrastre)
    eje_d = conveyor.get("eje_d")
    if eje_d and tambor_d:
        f_rad = 2.0 * pull_n
        span_eje = float(ancho)  # apoyo entre rodamientos ≈ ancho de banda
        sigma = shaft_bending_stress_mpa(f_rad, span_eje, float(eje_d))
        material = (frame or {}).get("material") or "acero"
        allow = yield_strength(material) / SHAFT_SAFETY
        calc_eje = {
            "titulo": "Flexión del eje del tambor",
            "entradas": {"carga radial": f"{f_rad:.1f} N (≈2×arrastre)",
                         "luz entre apoyos": f"{span_eje:.0f} mm",
                         "Ø eje": f"{float(eje_d):.0f} mm",
                         "σy": f"{yield_strength(material):.0f} MPa ({material})"},
            "formula": "σ = 32·(F·L/4) / (π·d³)",
            "sustitucion": f"σ = 32·({f_rad:.1f}·{span_eje:.0f}/4) / (π·{float(eje_d):.0f}³)",
            "resultado": f"σ = {sigma:.1f} MPa",
            "criterio": f"σ ≤ σy/{SHAFT_SAFETY:.0f} = {allow:.0f} MPa",
            "fs": round(allow / sigma, 2) if sigma > 0 else None,
        }
        det = (f"Eje Ø{float(eje_d):.0f} a flexión ≈ {sigma:.0f} MPa entre apoyos de {span_eje:.0f} mm "
               f"(admisible σy/{SHAFT_SAFETY:.0f} = {allow:.0f} MPa, {material}). Estimación.")
        if sigma <= allow:
            checks.append(_check("flexión del eje", "ok", det, calc=calc_eje))
        else:
            checks.append(_check(
                "flexión del eje", "error", det,
                "Usa un eje de mayor Ø o acerca los rodamientos (menor luz entre apoyos).",
                calc=calc_eje,
            ))

    return checks
