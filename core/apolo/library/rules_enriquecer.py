"""Detección de la faja, 2/2: el bastidor para la flecha y el ENRIQUECIMIENTO del dict
detectado con las variables del proyecto, los nombres y las fichas de catálogo (tambor, rpm,
motor a medida, eje, banda, soporte). Sale de `rules.py` (plan partir-nucleo-congelado-ii,
F3), que lo re-exporta por identidad. Puro: lee una escena, nunca un `Document`.
"""

from __future__ import annotations

import math

from .ancho_util import medir_banda
from .catalog import CATALOG
from .diametro_tambor import diametro_tambor
from .materials import density, piece_role, resolve_material
from .rules_comun import (
    EFFICIENCY, _BANDA_RE, _EJE_RE, _LARG_RE, _LEG_RE, _bbox_safe, _f, _name, _parse_diam,
    _parse_power_kw, _parse_wall, _vol_safe,
)


def _frame_from_scene(scene: dict, variables: dict | None) -> dict | None:
    """Extrae el bastidor para el chequeo de flecha: sección del larguero (ancho×alto,
    pared), material, VANO máximo entre patas, longitud total y peso transportado
    (estructura+banda+mesa, sin la carga del producto)."""
    v = variables or {}
    candidatas = [f for f in scene.values()
                  if "larguero" in _name(f) or "perfil" in _name(f)]
    if not candidatas:
        return None
    # los largueros REALES (los que reciben la flecha) llevan el ROL "larguero" (tras « · »:
    # «Faja de banda · Larguero (1)»), no las ménsulas que solo lo MENCIONAN. Sin ninguno
    # nombrado (bastidor de perfiles a mano) se cae al conteo permisivo de candidatas.
    beams = [f for f in candidatas if _LARG_RE.match(piece_role(_name(f)))] or candidatas
    f0 = beams[0]
    b = _bbox_safe(f0)
    if b is None:
        return None
    width = round(b.max.Y - b.min.Y, 1)   # ancho horizontal de la sección
    depth = round(b.max.Z - b.min.Z, 1)   # alto (dirección de la carga vertical)
    length = round(b.max.X - b.min.X, 1)  # longitud de la viga
    wall = _f(v.get("esp_larg")) or _parse_wall(getattr(f0, "name", "")) or 3.0
    material = resolve_material(f0)
    # vano: mayor hueco entre patas (apoyos); sin ≥2 patas → la longitud completa.
    # Solo cuentan las patas por ROL (no piezas que mencionan "pata"), para no meter
    # posiciones espurias en el reparto del vano.
    patas = [f for f in scene.values() if _LEG_RE.match(piece_role(_name(f)))]
    xs = sorted({round((bb.min.X + bb.max.X) / 2.0, 1)
                 for f in patas if (bb := _bbox_safe(f))})
    span = max((b2 - a for a, b2 in zip(xs, xs[1:])), default=0.0)
    if span <= 0:
        span = length
    # peso que carga el bastidor (estructura+banda+mesa); el producto se suma en el chequeo
    carried = 0.0
    for f in scene.values():
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
        "n_largueros": len(beams),
    }


def _enrich_conveyor(base: dict, scene: dict, variables: dict | None) -> dict:
    """Rellena los campos de ingeniería que faltan (tambor, rpm, motor a-medida, eje,
    bastidor) con las VARIABLES del proyecto y los nombres — para validar una faja hecha
    a mano cuyos datos no viven en componentes de catálogo. Solo rellena lo que falta."""
    v = variables or {}
    if not base.get("tambor_d"):
        td = _f(v.get("diam_tambor"))
        if td is None:
            td = diametro_tambor(f for f in scene.values()  # el Ø medido (F6)
                                 if any(w in _name(f) for w in ("rodillo", "tambor", "polea")))
        base["tambor_d"] = td
    if not base.get("rpm_motor"):
        rpm = _f(v.get("rpm_salida"))
        if rpm is None:
            rm, rr = _f(v.get("rpm_motor")), _f(v.get("ratio_red"))
            rpm = rm / rr if (rm and rr) else None
        base["rpm_motor"] = rpm
    if base.get("motor", "ninguno") == "ninguno":
        cands = [f for f in scene.values() if any(w in _name(f) for w in ("motor", "reductor"))]
        if cands:
            base["motor"] = "documento"
            # de todos los candidatos (motor + reductor), el de mayor potencia CONOCIDA:
            # specs de catálogo (potencia_kW — un NMRV insertado la lleva) o legible en el
            # nombre — así el "Motor 1.5HP" gana al "Reductor 1:30" (que no la lleva)
            kw, kw_comp, kw_nombre = 0.0, None, None
            for f in cands:
                comp = CATALOG.get(getattr(f, "component", None) or "")
                spec_kw = float((comp.specs or {}).get("potencia_kW") or 0.0) if comp else 0.0
                name_kw = _parse_power_kw(getattr(f, "name", "")) or 0.0
                if max(spec_kw, name_kw) > kw:
                    kw, kw_comp, kw_nombre = max(spec_kw, name_kw), comp, getattr(f, "name", None)
            if kw > 0:  # un motorreductor de catálogo trae sus rpm de salida (par, vida L10)
                from .relacion_motor import rpm_salida  # faja-compacta F1b: la «i = N» del sinfín

                base["motor_kW"] = kw
                base["rpm_motor"] = base.get("rpm_motor") or rpm_salida(kw_comp, kw_nombre)
                if not base.get("torque_Nm") and base.get("rpm_motor"):
                    omega = base["rpm_motor"] * 2.0 * math.pi / 60.0
                    if omega > 0:
                        # un sinfín-corona rinde ~0.7-0.8 (mucho menos que un helicoidal)
                        eff = 0.75 if (kw_comp is not None
                                       and kw_comp.category == "motorreductores_sinfin") else EFFICIENCY
                        base["torque_Nm"] = round(kw * 1000.0 * eff / omega, 1)
    if not base.get("eje_d"):
        # Ø del eje MOTRIZ (lo consume el check de flexión): sale del propio eje —nombre
        # «Ø35» o geometría del cilindro—, NO de la variable diam_eje que puede quedar
        # stale respecto al modelo. La variable es el ÚLTIMO recurso (faja sin geometría).
        # Solo piezas cuyo ROL es "eje" (no un tambor/rodillo/motor que lo mencionan).
        def _is_eje(f):
            name = _name(f)
            return bool(_EJE_RE.match(name.split("·")[-1].strip()) or _EJE_RE.match(name))

        ejes = [f for f in scene.values() if _is_eje(f)]

        def _eje_diam(f):
            d = _parse_diam(getattr(f, "name", "") or "")
            if d:
                return d
            bb = _bbox_safe(f)
            if bb is None:
                return None
            dims = sorted((bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z))
            # eje = cilindro: las dos extensiones menores (el Ø) casi iguales
            if dims[1] > 0 and abs(dims[0] - dims[1]) / dims[1] < 0.1:
                return round(dims[1], 1)
            return None

        # el eje MOTRIZ (por rol en el nombre) manda; si no, el de mayor Ø detectado
        motriz = next((f for f in ejes
                       if any(w in _name(f) for w in ("motriz", "motor"))), None)
        ed = _eje_diam(motriz) if motriz is not None else None
        if ed is None:
            cand = [d for f in ejes if (d := _eje_diam(f))]
            ed = max(cand) if cand else _f(v.get("diam_eje"))
        base["eje_d"] = ed
    if not base.get("banda_kg"):  # por ROL: el lazo, no cada pieza de «Faja de banda · …»
        bandas = [f for f in scene.values() if _BANDA_RE.match(piece_role(_name(f)))]
        kg = sum(_vol_safe(f) * density(resolve_material(f)) for f in bandas)
        if kg > 0:
            base["banda_kg"] = round(kg, 2)
    if base.get("frame") is None:
        base["frame"] = _frame_from_scene(scene, v)
    if base.get("tipo") == "banda":  # el ancho útil es el de la banda y sus guías, no el bbox
        base.update({k: x for k, x in medir_banda(scene).items() if k not in base})
    # --- señales normativas (V5.10): la regla elige el MÉTODO por construcción
    if "soporte" not in base and base.get("tipo") == "banda":
        # cama deslizante (slider bed) si hay mesa/cama; si no y hay
        # rodillos portantes → idlers; default honesto del vertical: cama
        tiene_cama = any(
            any(w in _name(f) for w in ("cama", "mesa", "desliz"))
            for f in scene.values()
        )
        base["soporte"] = "cama" if (tiene_cama or not base.get("n_rodillos")) else "rodillos"
    if "tambor_engomado" not in base:
        base["tambor_engomado"] = any(
            "tambor" in _name(f)
            and any(w in _name(f) for w in ("engomado", "lagging", "goma"))
            for f in scene.values()
        )
    # `tiene_tensor` ya NO sale del nombre de una pieza (plan puerta-de-publicacion D3): lo pone
    # el documento con el tensor RECONOCIDO (`services/engineering_rules.inherit_tensor`)
    if not base.get("q_ro_kg_m") and base.get("largo"):
        # masa por metro de partes giratorias (rodillos de catálogo, por FICHA)
        kg = 0.0
        for f in scene.values():
            comp = CATALOG.get(getattr(f, "component", None) or "")
            if comp is not None and comp.category == "rodillos":
                kg += float(comp.weight or 0.0)
        if kg > 0:
            base["q_ro_kg_m"] = round(kg / (base["largo"] / 1000.0), 3)
    return base
