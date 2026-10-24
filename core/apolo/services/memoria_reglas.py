"""Las reglas de la MEMORIA DE CÁLCULO de un documento, sin componer el PDF: la fuente única del
endpoint `GET /api/calc-report.pdf` y del ítem «memoria» de la puerta de publicación (plan
puerta-de-publicacion, D2: la memoria en «NO CONFORME» bloquea). Sus diferencias con `/api/checks`
son deliberadas (`services/CLAUDE.md` § Reglas de ingeniería). El llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

ALCANCE = {
    "regla": "alcance de la memoria",
    "estado": "aviso",
    "detalle": "Sin `carga_kg` / `largo_paquete_mm` declarados: se OMITEN las "
               "verificaciones de transportador (arrastre, adherencia del tambor, "
               "capacidad, velocidad). Lo verificado aquí es estructural y de "
               "uniones.",
    "recomendacion": "Declara los requisitos con set_requirements si el equipo "
                     "transporta producto.",
}


def reglas_memoria(doc, carga_kg=None, largo_paquete_mm=None, ancho_paquete_mm=None,
                   velocidad_m_s=None) -> tuple[list[dict], dict]:
    """(reglas, requisitos efectivos de la portada). Los parámetros explícitos ganan a los
    requisitos guardados. Sin carga ni largo de paquete se omiten las reglas de transportador y se
    DECLARA lo omitido (una memoria que calla lo que no verificó miente por ausencia)."""
    from apolo.library.rules import conveyor_engineering_check as conv_check
    from apolo.library.rules import detect_conveyor

    from .engineering_rules import (
        conveyor_params_from_doc,
        inherit_inclination,
        inherit_tensor,
        requirement_inputs,
        structure_rules,
    )
    from . import neumatica
    from .stackup_eval import stackup_rules

    req, carga, largo_paq, ancho_paq = requirement_inputs(
        doc, carga_kg, largo_paquete_mm, ancho_paquete_mm)
    velocidad = velocidad_m_s if velocidad_m_s is not None else float(req.get("velocidad_m_s") or 0)
    sin_req_conveyor = not carga or not largo_paq
    rules: list[dict] = []
    conveyor = None if sin_req_conveyor else (
        conveyor_params_from_doc(doc) or detect_conveyor(doc.scene, doc.variables_resolved,
                                                         doc.fasteners))
    if conveyor:
        inherit_inclination(conveyor, req)
        inherit_tensor(doc, conveyor)
        rules += conv_check(conveyor, carga_kg=carga, largo_paquete_mm=largo_paq,
                            velocidad_m_s=velocidad, ancho_paquete_mm=ancho_paq)
    rules += structure_rules(doc, carga, conveyor)  # estructura/uniones/vuelco + FEA (vigencia)
    rules += stackup_rules(doc)  # V7.3: cadenas de cotas declaradas/auto
    rules += neumatica.memoria(doc)  # V8.9 D10: el aire (sin aire, nada)
    if sin_req_conveyor:
        rules.append(dict(ALCANCE))
    # sin requisitos de transportador NO se inyectan claves vacías a la portada
    efectivos = dict(req)
    for clave, valor in (("carga_kg", carga), ("largo_paquete_mm", largo_paq),
                         ("ancho_paquete_mm", ancho_paq), ("velocidad_m_s", velocidad)):
        if valor:
            efectivos[clave] = valor
    return rules, efectivos


def veredicto_memoria(doc) -> dict:
    """{veredicto, reglas, errores}: lo que la portada de la memoria diría, sin el PDF."""
    from apolo.drawing.calc_report import veredicto

    rules, _ = reglas_memoria(doc)
    errores = [{"regla": r.get("regla"), "detalle": r.get("detalle")}
               for r in rules if r.get("estado") == "error"]
    return {"veredicto": veredicto(rules), "reglas": len(rules), "errores": errores}
