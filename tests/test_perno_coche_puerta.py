"""La puerta mide el perno de CABEZA ABOMBADA (de coche, DIN 603): su cúpula es una cara esférica y
el cuello es cuadrado, sin hexágono ni cilindro de cabeza; antes salía «vástago sin cabeza
modelada» y los ítems de agarre quedaban SIN_EVALUAR sin salida (rodillos-cadena F9, piloto
2026-10-29)."""

from __future__ import annotations

import pytest

from apolo.doc.document import Document
from apolo.services.calidad_pernos import geometria_perno


@pytest.mark.parametrize("largo", [40.0, 70.0])
def test_perno_de_coche_se_reconoce(largo):
    doc = Document("t")
    doc.execute("insert_component", {"name": "Perno M10 DIN 603", "component": "PERNO-COCHE-M10",
                                     "length": largo})
    solido = next(iter(doc.scene.values())).shape.solids()[0]
    g = geometria_perno(solido)
    assert g is not None and g["cabeza"] == "coche"
    assert g["d"] == pytest.approx(10.0)
    assert g["largo"] == pytest.approx(largo, abs=0.5)
    assert g["s"] > 2 * g["d"]  # la cúpula apoya más ancha que el vástago


def test_perno_hex_sigue_igual():
    doc = Document("t")
    doc.execute("insert_component", {"name": "Perno M10", "component": "PERNO-HEX-M10",
                                     "length": 40.0})
    g = geometria_perno(next(iter(doc.scene.values())).shape.solids()[0])
    assert g is not None and g["cabeza"] == "hex"
