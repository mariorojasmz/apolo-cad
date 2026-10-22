"""Los ítems de FUNCIÓN MECÁNICA de la puerta de publicación (plan puerta-de-publicacion, F2):
agarre de perno, tensor y vida útil, sobre un documento. Es lo que la F1 registra: lee el
documento (insumos de `calidad_pernos` y `calidad_tensores`), corre las reglas de ingeniería como
`/api/checks` y pasa todo a los controles PUROS de `library/calidad/`. El llamador sostiene
STATE_LOCK.
"""

from __future__ import annotations

_MOTORES = ("motorreductores", "motorreductores_sinfin")


def reglas_de_ingenieria(doc) -> list[dict]:
    """Las reglas que da `/api/checks` (transportador con los requisitos guardados + estructura
    universal + lints), sin interferencias: la entrada de `controlar_vida_util`."""
    from apolo.commands.expressions import resolve_params
    from apolo.library import conveyor_engineering_check
    from apolo.library.lints import predelivery_lints
    from apolo.library.rules import detect_conveyor

    from .engineering_rules import (
        conveyor_params_from_doc,
        inherit_inclination,
        inherit_tensor,
        requirement_inputs,
        structure_rules,
    )

    req, carga, largo_paq, ancho_paq = requirement_inputs(doc, None, None, None)
    reglas: list[dict] = []
    conveyor = None
    if carga and largo_paq:
        conveyor = conveyor_params_from_doc(doc) or detect_conveyor(
            doc.scene, doc.variables_resolved, doc.fasteners)
        inherit_inclination(conveyor, req)
        inherit_tensor(doc, conveyor)
        if conveyor:
            reglas += conveyor_engineering_check(
                conveyor, carga_kg=carga, largo_paquete_mm=largo_paq,
                velocidad_m_s=float(req.get("velocidad_m_s") or 0), ancho_paquete_mm=ancho_paq)
    reglas += structure_rules(doc, carga, conveyor)
    reglas += predelivery_lints(
        doc.scene, doc.commands, doc.fasteners, doc.grounds, doc.joints, doc.mates,
        resolve=lambda p: resolve_params(p, doc.variables_resolved))
    return reglas


def items_funcion_mecanica(doc, reglas: list[dict] | None = None, *, contexto=None) -> list:
    """Los ítems (`library/calidad/item.Item`) de agarre, tensor y vida útil del documento.
    `reglas` = las de `engineering_check` si el llamador ya las tiene; `contexto` (el memo de la
    corrida de la puerta, protocolo de las fuentes del registro) no lo usa."""
    from apolo.library.calidad.agarre import controlar_agarre
    from apolo.library.calidad.tensor import controlar_tensores
    from apolo.library.calidad.vida_util import controlar_vida_util
    from apolo.library.catalog import CATALOG

    from .calidad_pernos import insumos_pernos
    from .calidad_tensores import lazos

    if reglas is None:
        reglas = reglas_de_ingenieria(doc)
    hay_motor = any((c := CATALOG.get(getattr(f, "component", None) or "")) is not None
                    and c.category in _MOTORES for f in doc.scene.values())
    hay_uniones = any(f.get("kind", "perno") in ("perno", "soldadura")
                      for f in doc.fasteners.values())
    return (controlar_agarre(insumos_pernos(doc)) + controlar_tensores(lazos(doc))
            + controlar_vida_util(reglas, hay_motor=hay_motor, hay_uniones=hay_uniones))
