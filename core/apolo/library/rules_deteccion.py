"""Detección de la faja, 1/2: infiere el dict de `conveyor_engineering_check` de una faja
HECHA A MANO (por catálogo, por nombres o por un grupo explícito de sólidos). Sale de
`rules.py` (plan partir-nucleo-congelado-ii, F3), que lo re-exporta por identidad. Puro.
"""

from __future__ import annotations

from collections import Counter

from .catalog import CATALOG
from .diametro_tambor import diametro_tambor
from .rules_comun import _bbox_safe
from .rules_enriquecer import _enrich_conveyor


def detect_conveyor(scene: dict, variables: dict | None = None, fasteners=None) -> dict | None:
    """Infiere los parámetros de una faja HECHA A MANO a partir de sus piezas
    (no del super-comando create_conveyor). Devuelve el mismo dict que consume
    conveyor_engineering_check (+ tipo/tambor_d/rpm_motor/torque_Nm/n_rodillos/frame),
    o None si la escena no parece una faja. `variables` (las del proyecto) enriquece
    la detección (Ø tambor, rpm, motor a-medida, eje, bastidor para la flecha).

    Patrón: ≥1 motorreductor de catálogo Y ≥1 perfil Y (≥1 rodillo de catálogo O
    ≥1 tambor sin componente con 'tambor' en el nombre); si no, `rodillos_a_mano` y los nombres."""
    motors: list = []
    rollers: list = []
    perfiles: list = []
    tambores: list = []
    for feat in scene.values():
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
        from .rodillos_a_mano import detectar_rodillos_a_mano  # rodillo de tubo, bastidor de ángulo
        return detectar_rodillos_a_mano(scene, fasteners) or _detect_by_name(scene, variables)
    _bb = _bbox_safe

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

    tambor_d = diametro_tambor(tambores)  # el Ø de la cara motriz, no el de su guarda (F6)

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


def _detect_by_name(scene: dict, variables: dict | None = None) -> dict | None:
    """Respaldo: infiere una faja hecha 100% con primitivas a partir de los NOMBRES
    de las piezas (sin componentes de catálogo). Patrón mínimo: una banda o un
    tambor + alguna estructura (larguero/perfil/bastidor). `variables` enriquece
    motor/tambor/rpm/eje/bastidor."""
    def has(*words):
        return [
            f for f in scene.values()
            if any(w in (getattr(f, "name", "") or "").lower() for w in words)
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
    tambor_d = diametro_tambor(tambores)
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
    tambor_d = diametro_tambor(tambores)
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
