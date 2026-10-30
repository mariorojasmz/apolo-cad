"""`material.conocido` (plan hallazgos-del-revisor-en-la-puerta, D1): un material que el núcleo no
conoce es FALLA, nunca acero en silencio. Puro: juzga el insumo `fabricacion.desconocidos` que
arma `services/puerta_hechos.fabricacion`.

Toda pieza A MEDIDA (sin ref de catálogo: la ref pesa por su ficha y no se juzga) cuyo material
resuelto (`materials.resolve_material` con el vertical del documento) no reconoce
`materials.known_material` se pesa, se costea y se dimensiona con los defaults del ACERO
(`DEFAULT_DENSITY`, `DEFAULT_YIELD`): una tijera de haya pesaba 6,9 kg en vez de 0,62. Sólo se
exige la densidad tabulada (F0 del plan): la resistencia la exige el cálculo que la usa (el FEA,
`has_yield`), no la puerta; si no, una banda de PVC tumbaba la faja testigo.

Fuera de la puerta nada cambia: la BOM y la masa siguen con el default y `set_material` ya avisa
(`aviso_material`). Una especie nueva se TABULA con su fuente en `materials.py`, nunca por defecto.
"""

from __future__ import annotations

from .entrada import Entrada, hay
from .item import FALLA, OK, SIN_EVALUAR, recortar


def _r(estado: str, detalle: str, evidencia: dict, piezas=()) -> dict:
    return {"estado": estado, "detalle": detalle, "evidencia": evidencia,
            "piezas": list(dict.fromkeys(piezas))[:40]}


def material_conocido(ins: dict) -> dict:
    """`ins["fabricacion"]` = {piezas, catalogo, desconocidos: [{id, nombre, material}]}."""
    fab = ins.get("fabricacion") or {}
    desconocidos = fab.get("desconocidos")
    if desconocidos is None:
        return _r(SIN_EVALUAR, "no se resolvió el material de las piezas", {})
    a_medida = int(fab.get("piezas", 0)) - int(fab.get("catalogo", 0))
    ev = {"a_medida": a_medida, "de_catalogo": fab.get("catalogo", 0), "elemento": "pieza"}
    if desconocidos:
        materiales = sorted({str(d.get("material")) for d in desconocidos})
        ejemplo = desconocidos[0]
        return _r(FALLA, f"{len(desconocidos)} pieza(s) a medida con un material que el núcleo no "
                         f"tiene tabulado ({', '.join(f'«{m}»' for m in materiales[:6])}): se "
                         f"pesarían y calcularían como ACERO. Primera: {ejemplo.get('nombre')}. "
                         "Asígnales un material conocido (set_material) o tabula la especie con su "
                         "fuente en library/materials.py",
                  {**ev, "materiales": materiales, **recortar(desconocidos)},
                  [d.get("id") for d in desconocidos])
    return _r(OK, f"{a_medida} pieza(s) a medida, todas con un material de densidad tabulada", ev)


ENTRADA = Entrada(
    "material.conocido",
    "Cada pieza a medida tiene un material con densidad tabulada",
    "un material que el núcleo no conoce se pesa, se costea y se dimensiona como acero sin "
    "decirlo: la BOM, la masa y la memoria publican cifras falsas",
    "criterio de diseño (D1 de hallazgos-del-revisor-en-la-puerta)", "proceso",
    hay("piezas", "el modelo no tiene piezas"), material_conocido, "piezas")
