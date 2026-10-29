"""El concreto pesa como concreto (EN 1991-1-1 anexo A: 24 kN/m³), no como acero: una zapata de
lastre con material «concreto» se pesaba 3,3× (densidad por defecto del acero) y el levantamiento
por viento quedaba del lado inseguro (re-revisión del soporte de paneles, 2026-10-29)."""

from __future__ import annotations

import pytest

from apolo.library.apariencia import acabado_de
from apolo.library.materials import DEFAULT_DENSITY, density


@pytest.mark.parametrize("material", ["concreto", "Concreto f'c 210", "hormigón", "hormigon armado"])
def test_concreto_y_hormigon_pesan_2400(material):
    assert density(material) == pytest.approx(2.4e-6)
    assert density(material) < DEFAULT_DENSITY / 3


def test_concreto_se_ve_como_concreto():
    assert acabado_de("concreto") == "concreto"
    assert acabado_de("hormigón") == "concreto"
