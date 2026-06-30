"""Fórmulas estructurales puras (inercia / flecha / flexión) y props de material."""

import math

import pytest

from apolo.library.materials import young_modulus, yield_strength
from apolo.library.structural import (
    beam_udl_deflection_mm,
    rect_tube_inertia_mm4,
    shaft_bending_stress_mpa,
)


def test_rect_tube_inertia():
    # tubo 40×80 pared 3: I = (40·80³ − 34·74³)/12
    i = rect_tube_inertia_mm4(40, 80, 3)
    assert i == pytest.approx((40 * 80**3 - 34 * 74**3) / 12.0, rel=1e-9)
    # pared gruesa → tiende a la sección maciza
    assert rect_tube_inertia_mm4(40, 80, 40) == pytest.approx(40 * 80**3 / 12.0, rel=1e-9)


def test_beam_udl_deflection():
    d = beam_udl_deflection_mm(1.0, 1000, 200000, 1e6)
    assert d == pytest.approx(5 * 1.0 * 1000**4 / (384 * 200000 * 1e6), rel=1e-9)
    # más vano → mucha más flecha (L⁴); E o I nulos → 0 (defensivo)
    assert beam_udl_deflection_mm(1.0, 2000, 200000, 1e6) > 10 * d
    assert beam_udl_deflection_mm(1.0, 1000, 0, 1e6) == 0.0


def test_shaft_bending_stress():
    s = shaft_bending_stress_mpa(1000, 1000, 35)
    assert s == pytest.approx(32 * (1000 * 1000 / 4) / (math.pi * 35**3), rel=1e-9)
    assert shaft_bending_stress_mpa(1000, 1000, 0) == 0.0


def test_material_mechanical_props():
    assert young_modulus("acero") == 200000.0
    assert young_modulus("aluminio") == 69000.0
    assert young_modulus("Larguero A36 acero") == 200000.0  # _norm reconoce 'acero'
    assert young_modulus("desconocido") == 200000.0         # default acero
    assert yield_strength("acero") == 250.0
    assert yield_strength("aluminio") == 240.0
