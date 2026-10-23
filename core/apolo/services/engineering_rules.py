"""Reglas de ingeniería de un documento: lo que `/api/checks` y la memoria de cálculo
COMPARTEN de verdad (bases de diseño desde los requisitos, inclinación heredada, chequeo
estructural universal + FEA con vigencia) y los parámetros de la faja paramétrica, que usan
también la tool `engineering_check` del agente. Sus DIFERENCIAS son deliberadas y quedan en
cada endpoint (velocidad con `or` vs `is not None`, lints sólo en checks, stack-up y «alcance»
sólo en la memoria). El llamador sostiene STATE_LOCK. Reglas: `services/CLAUDE.md`."""

from __future__ import annotations


def conveyor_params_from_doc(doc) -> dict | None:
    """Los params del ÚLTIMO transportador paramétrico del log: un `create_conveyor` o un
    `create_roller_conveyor` (éste con `plantilla`, que `conveyor_engineering_check` valida con
    sus reglas propias contra la ficha; plan plantilla-rodillos-cadena D9)."""
    from apolo.commands import resolve_params

    tipos = ("create_conveyor", "create_roller_conveyor")
    cmd = next((c for c in reversed(doc.commands) if c["type"] in tipos), None)
    if cmd is None:
        return None
    params = resolve_params(cmd["params"], doc.variables_resolved)
    if cmd["type"] == "create_roller_conveyor":
        from apolo.commands.models_rodillos_cadena import CreateRollerConveyorParams

        try:
            params = CreateRollerConveyorParams.model_validate(params, extra="ignore").model_dump(
                exclude={"position"})
        except ValueError:  # params rotos: las reglas lo dicen como error, sin tumbar el chequeo
            pass
        return {"plantilla": cmd["type"], **params}
    defaults = {"largo": 2000, "ancho": 600, "altura": 750, "paso": 100, "rodillo": "RODILLO-50", "motor": "ninguno"}
    return {**defaults, **params}


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


def inherit_tensor(doc, conveyor: dict | None) -> None:
    """La adherencia de Eytelwein sabe si hay tensor por el RECONOCIMIENTO de la puerta de
    publicación (`calidad_tensores`: take-up, unidad de catálogo, ranuras de la plantilla o el
    metadato `tensores`), nunca por el nombre de una pieza (plan puerta-de-publicacion D3). Un
    `tiene_tensor` explícito del cliente gana (muta)."""
    if conveyor and "tiene_tensor" not in conveyor:
        from .calidad_tensores import tiene_tensor_reconocido

        conveyor["tiene_tensor"] = tiene_tensor_reconocido(doc)


def structure_rules(doc, carga, conveyor: dict | None) -> list[dict]:
    """Chequeo estructural UNIVERSAL (pernos/soldaduras/L10/pandeo/vuelco): aplica a
    cualquier ensamblaje, no exige carga ni faja detectada; más la flecha de las vigas del
    bastidor (`vigas_rules`), la transmisión por cadena de cada `create_chain` y los
    resultados FEA guardados (con chequeo de vigencia). Llamar bajo STATE_LOCK."""
    from apolo.library.engineering.report import structure_engineering_check

    from .fea_rules import fea_rules
    from .transmision_rules import chain_rules
    from .vigas_rules import beam_rules

    rules = structure_engineering_check(
        doc.scene, doc.fasteners, doc.grounds, doc.joints, doc.mates,
        carga_kg=carga or 0.0,
        rpm=(conveyor or {}).get("rpm_motor"),
        belt_radial_n=(conveyor or {}).get("bearing_radial_n"),
        default_material=doc.default_material(),  # la masa de mass-properties (F6)
    )
    rules += beam_rules(doc, carga)
    rules += chain_rules(doc)
    rules += fea_rules(doc)
    return rules
