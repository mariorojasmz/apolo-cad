"""Reglas de ingeniería de un documento: lo que `/api/checks` y la memoria de cálculo
COMPARTEN de verdad (bases de diseño desde los requisitos, inclinación heredada, chequeo
estructural universal + FEA con vigencia) y los parámetros de la faja paramétrica, que usan
también la tool `engineering_check` del agente. Sus DIFERENCIAS son deliberadas y quedan en
cada endpoint (velocidad con `or` vs `is not None`, lints sólo en checks, stack-up y «alcance»
sólo en la memoria). El llamador sostiene STATE_LOCK. Reglas: `services/CLAUDE.md`."""

from __future__ import annotations


def conveyor_params_from_doc(doc) -> dict | None:
    from apolo.commands import resolve_params

    cmd = next((c for c in reversed(doc.commands) if c["type"] == "create_conveyor"), None)
    if cmd is None:
        return None
    defaults = {"largo": 2000, "ancho": 600, "altura": 750, "paso": 100, "rodillo": "RODILLO-50", "motor": "ninguno"}
    return {**defaults, **resolve_params(cmd["params"], doc.variables_resolved)}


def requirement_inputs(doc, carga_kg, largo_paquete_mm, ancho_paquete_mm) -> tuple:
    """`(req, carga, largo_paq, ancho_paq)`: los REQUISITOS guardados (bases de diseño)
    rellenan lo que la llamada no trae — los parámetros explícitos siempre GANAN."""
    req = doc.requirements or {}
    carga = carga_kg if carga_kg is not None else req.get("carga_kg")
    largo_paq = (largo_paquete_mm if largo_paquete_mm is not None
                 else req.get("largo_paquete_mm"))
    ancho_paq = (ancho_paquete_mm if ancho_paquete_mm is not None
                 else req.get("ancho_paquete_mm"))
    return req, carga, largo_paq, ancho_paq


def inherit_inclination(conveyor: dict | None, req: dict) -> None:
    """La faja hereda la inclinación de los requisitos si no declara la suya (muta)."""
    if conveyor and req.get("inclinacion_deg") and not conveyor.get("inclinacion_deg"):
        conveyor["inclinacion_deg"] = req["inclinacion_deg"]


def structure_rules(doc, carga, conveyor: dict | None) -> list[dict]:
    """Chequeo estructural UNIVERSAL (pernos/soldaduras/L10/pandeo/vuelco): aplica a
    cualquier ensamblaje, no exige carga ni faja detectada; más los resultados FEA guardados
    (con chequeo de vigencia). Llamar bajo STATE_LOCK."""
    from apolo.library.engineering.report import structure_engineering_check

    from .fea_rules import fea_rules

    rules = structure_engineering_check(
        doc.scene, doc.fasteners, doc.grounds, doc.joints, doc.mates,
        carga_kg=carga or 0.0,
        rpm=(conveyor or {}).get("rpm_motor"),
        belt_radial_n=(conveyor or {}).get("bearing_radial_n"),
    )
    rules += fea_rules(doc)
    return rules
