"""Tests del paquete engineering/ (Frente A, Fase 1): funciones puras de
dimensionamiento + datos nuevos de catálogo (C_kN, grado)."""

from __future__ import annotations

import math

import pytest

from apolo.library.catalog import CATALOG
from apolo.library.engineering import (
    BED_FRICTION,
    GRADES,
    TENSILE_AREA_MM2,
    belt_power_kw,
    belt_pull_n,
    belt_startup_torque_nm,
    bolt_shear_capacity_n,
    bolt_tension_capacity_n,
    bolt_utilization,
    convex_hull_2d,
    estimate_belt_kg,
    euler_critical_load_n,
    hanging_load_kg,
    hull_margin_mm,
    l10_hours,
    rect_tube_min_inertia_mm4,
    weld_allowable_mpa,
    weld_throat_stress_mpa,
)
from apolo.library.structural import rect_tube_inertia_mm4


# ------------------------------------------------------------------ belt
def test_belt_pull_flat():
    # 30 kg de carga + 10 kg de banda, plano: F = 9.81·0.33·40 = 129.5 N
    f = belt_pull_n(30, banda_kg=10)
    assert f == pytest.approx(9.81 * BED_FRICTION * 40.0, rel=1e-9)


def test_belt_pull_incline_adds_gravity_component():
    plano = belt_pull_n(30)
    inclinado = belt_pull_n(30, incline_deg=10)
    assert inclinado == pytest.approx(plano + 9.81 * 30 * math.sin(math.radians(10)), rel=1e-9)


def test_belt_power_and_startup_torque():
    # F=200 N, v=0.5 m/s, η=0.85, margen 1.3 → P = 200·0.5/0.85/1000·1.3 ≈ 0.153 kW
    assert belt_power_kw(200, 0.5) == pytest.approx(200 * 0.5 / 0.85 / 1000 * 1.3, rel=1e-9)
    # tambor Ø114: T = 200·0.057·1.6 = 18.24 N·m
    assert belt_startup_torque_nm(200, 114) == pytest.approx(200 * 0.057 * 1.6, rel=1e-9)


def test_estimate_belt_kg():
    # 4000×600×2 mm ida+retorno a ρ 1.4e-6 → 2·4000·600·2·1.4e-6 = 13.44 kg
    assert estimate_belt_kg(4000, 600) == pytest.approx(13.44, rel=1e-9)


def test_belt_friction_much_higher_than_rolling():
    # a igual carga, la banda sobre cama exige más fuerza que el μ=0.06 de rodadura
    assert belt_pull_n(100) > 100 * 9.81 * 0.06 * 2


# ----------------------------------------------------------------- bolts
def test_bolt_shear_capacity_m10_88():
    # Fv = 0.6·800·58.0/1.25 = 22 272 N
    assert bolt_shear_capacity_n("M10", "8.8") == pytest.approx(22272.0, rel=1e-6)


def test_bolt_tension_capacity_m12():
    # Ft = 0.9·800·84.3/1.25 = 48 556.8 N
    assert bolt_tension_capacity_n("M12", "8.8") == pytest.approx(0.9 * 800 * 84.3 / 1.25, rel=1e-9)


def test_bolt_high_grade_uses_alpha_05():
    # 10.9 usa αv=0.5: Fv = 0.5·1000·58/1.25 = 23 200 (no 0.6)
    assert bolt_shear_capacity_n("M10", "10.9") == pytest.approx(23200.0, rel=1e-6)


def test_bolt_utilization_splits_load():
    cap = bolt_shear_capacity_n("M10")
    assert bolt_utilization(cap * 2, "M10", qty=2) == pytest.approx(1.0, rel=1e-9)
    assert bolt_utilization(cap / 2, "M10", qty=1) == pytest.approx(0.5, rel=1e-9)


def test_bolt_unknown_size_raises():
    with pytest.raises(KeyError):
        bolt_shear_capacity_n("M7")
    with pytest.raises(KeyError):
        bolt_shear_capacity_n("M10", grade="9.9")


def test_bolt_tables_cover_expected_range():
    assert set(TENSILE_AREA_MM2) >= {"M6", "M8", "M10", "M12", "M16", "M20"}
    assert GRADES["8.8"] == (800.0, 640.0)


# ----------------------------------------------------------------- welds
def test_weld_stress_and_allowable():
    # F=10 kN, a=4 mm, L=100 mm → τ = 10000/400 = 25 MPa; admisible acero 0.6·250=150
    assert weld_throat_stress_mpa(10000, 4, 100) == pytest.approx(25.0)
    assert weld_allowable_mpa(250.0) == pytest.approx(150.0)


def test_weld_zero_area_is_infinite():
    assert weld_throat_stress_mpa(100, 0, 100) == float("inf")


# -------------------------------------------------------------- bearings
def test_l10_hours_manual_value():
    # 6204: C=12.7 kN, P=2 kN, 100 rpm → (6.35)³·1e6/6000 ≈ 42 672 h
    assert l10_hours(12.7, 2.0, 100) == pytest.approx((12.7 / 2.0) ** 3 * 1e6 / 6000.0, rel=1e-9)


def test_l10_no_load_or_rpm_is_infinite():
    assert l10_hours(12.7, 0, 100) == float("inf")
    assert l10_hours(12.7, 2.0, 0) == float("inf")


# -------------------------------------------------------------- buckling
def test_euler_critical_load_leg():
    # pata 80×80×3, L=700, K=2, E=200000: Pcr = π²·E·I/(KL)²
    i = rect_tube_min_inertia_mm4(80, 80, 3)
    expected = math.pi**2 * 200000 * i / (2 * 700) ** 2
    assert euler_critical_load_n(200000, i, 700, k=2.0) == pytest.approx(expected, rel=1e-9)
    # una pata real aguanta MUCHO más que su cuota de carga típica (~100 kg)
    assert expected > 100 * 9.81 * 10


def test_min_inertia_of_rect_section():
    # sección 80×40: el eje débil manda
    weak = rect_tube_min_inertia_mm4(101.6, 50.8, 3)
    assert weak == pytest.approx(rect_tube_inertia_mm4(101.6, 50.8, 3))
    assert weak < rect_tube_inertia_mm4(50.8, 101.6, 3)


# ------------------------------------------------------------- stability
def test_convex_hull_square_with_interior_point():
    pts = [(0, 0), (100, 0), (100, 100), (0, 100), (50, 50)]
    hull = convex_hull_2d(pts)
    assert len(hull) == 4
    assert (50, 50) not in hull


def test_hull_margin_inside_and_outside():
    hull = convex_hull_2d([(0, 0), (100, 0), (100, 100), (0, 100)])
    assert hull_margin_mm((50, 50), hull) == pytest.approx(50.0)
    assert hull_margin_mm((10, 50), hull) == pytest.approx(10.0)
    assert hull_margin_mm((-20, 50), hull) == pytest.approx(-20.0)


def test_hull_margin_degenerate_never_positive():
    assert hull_margin_mm((5, 5), []) == float("-inf")
    assert hull_margin_mm((3, 4), [(0.0, 0.0)]) == pytest.approx(-5.0)
    assert hull_margin_mm((5, 5), [(0.0, 0.0), (10.0, 0.0)]) == pytest.approx(-5.0)


# ----------------------------------------------------------------- loads
def _graph(adj_pairs, seeds, ids):
    adj = {i: set() for i in ids}
    for a, b in adj_pairs:
        adj[a].add(b)
        adj[b].add(a)
    return {"adj": adj, "grounded_seed": set(seeds), "ids": set(ids)}


def test_hanging_load_simple_chain():
    # piso ← base ← viga ← motor (10 kg): el fastener base↔viga carga viga+motor
    g = _graph([("base", "viga"), ("viga", "motor")], {"base"}, ["base", "viga", "motor"])
    masses = {"base": 50.0, "viga": 5.0, "motor": 10.0}
    assert hanging_load_kg(g, masses, "base", "viga") == pytest.approx(15.0)
    assert hanging_load_kg(g, masses, "viga", "motor") == pytest.approx(10.0)


def test_hanging_load_redundant_returns_none():
    # el motor cuelga de DOS vigas → quitar una unión no lo suelta: indeterminado
    g = _graph(
        [("base", "v1"), ("base", "v2"), ("v1", "motor"), ("v2", "motor")],
        {"base"},
        ["base", "v1", "v2", "motor"],
    )
    assert hanging_load_kg(g, {"motor": 10.0}, "v1", "motor") is None


def test_hanging_load_no_ground_returns_none():
    g = _graph([("a", "b")], set(), ["a", "b"])
    assert hanging_load_kg(g, {"a": 1, "b": 2}, "a", "b") is None


# --------------------------------------------------------------- catálogo
def test_bearing_catalog_has_dynamic_capacity():
    assert CATALOG["6204"].specs["C_kN"] == 12.7
    assert CATALOG["6205"].specs["C_kN"] == 14.0
    assert CATALOG["6207"].specs["C_kN"] == 25.5
    # todas las variantes de rodamiento llevan C_kN
    for comp in CATALOG.values():
        if comp.category == "rodamientos":
            assert comp.specs.get("C_kN", 0) > 0, comp.ref


def test_pillow_block_catalog_has_dynamic_capacity():
    assert CATALOG["UCP205"].specs["C_kN"] == 14.0
    assert CATALOG["UCF207"].specs["C_kN"] == 25.5
    assert CATALOG["UCFL208"].specs["C_kN"] == 30.7


def test_bolt_catalog_has_structured_grade():
    assert CATALOG["PERNO-M10"].specs["grado"] == "8.8"
