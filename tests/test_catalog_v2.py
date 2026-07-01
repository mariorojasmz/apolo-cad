"""V2: familias nuevas de catálogo (chumaceras, topes, pies niveladores, tensores)
añadidas data-driven — cargan, construyen geometría y aparecen en los enums."""
import pytest

from apolo.commands.models import InsertComponentParams
from apolo.library.catalog import CATALOG, build_component

NUEVOS = {
    "UCP205": "chumaceras",
    "UCP206": "chumaceras",
    "UCF207": "chumaceras",
    "UCFL207": "chumaceras",
    "TOPE-M6-30": "topes",
    "TOPE-M8-40": "topes",
    "TOPE-M10-50": "topes",
    "PIE-M8-30": "pies_niveladores",
    "PIE-M10-40": "pies_niveladores",
    "PIE-M12-50": "pies_niveladores",
    "TENSOR-40": "transmision",
    "TENSOR-50": "transmision",
    "TENSOR-60": "transmision",
}


@pytest.mark.parametrize("ref,categoria", NUEVOS.items())
def test_nuevo_componente_carga_y_construye(ref, categoria):
    comp = CATALOG[ref]
    assert comp.category == categoria
    assert comp.weight > 0
    shape, cut = build_component(ref)
    assert shape.volume > 0
    assert cut is None  # no cortables


def test_nuevos_en_enum_insert_component():
    enum = InsertComponentParams.model_json_schema()["properties"]["component"]["enum"]
    for ref in NUEVOS:
        assert ref in enum


def test_chumacera_tiene_agujero_de_eje():
    """La chumacera debe tener el taladro del rodamiento (anillo, no disco macizo)."""
    macizo, _ = build_component("UCP205")
    # el volumen es bastante menor que el de su bbox (placa + anillo con hueco)
    bb = macizo.bounding_box()
    caja = bb.size.X * bb.size.Y * bb.size.Z
    assert macizo.volume < 0.7 * caja
