"""V7.3 — motor de stack-up de cadenas de cotas 1D (peor caso + RSS)."""

import math

import pytest

from apolo.library.engineering.fits import fit_check
from apolo.library.engineering.stackup import (
    bolt_pattern_budget, iso2768_linear, stack_up,
)


# ---------------------------------------------------------------- ISO 2768 lineal
def test_iso2768_linear_by_range_and_class():
    assert iso2768_linear(10, "m") == 0.2   # 6–30 mm, media
    assert iso2768_linear(10, "f") == 0.1   # fina
    assert iso2768_linear(10, "c") == 0.5   # grosera
    assert iso2768_linear(200, "m") == 0.5  # 120–400 mm
    assert iso2768_linear(3000, "m") == 2.0  # 2000–4000 mm


def test_iso2768_out_of_range_and_bad_class():
    with pytest.raises(KeyError):
        iso2768_linear(5000, "m")   # > 4000 mm
    with pytest.raises(KeyError):
        iso2768_linear(10, "z")     # clase inválida


# ---------------------------------------------------- ancla dura contra ISO 286
def test_fit_chain_reproduces_iso286_clearance_exactly():
    """Cadena AGUJERO H7 (+1) − EJE h7 (−1) sobre Ø20: el intervalo de cierre debe
    reproducir EXACTAMENTE el juego min/max de fit_check (ancla contra la tabla)."""
    fc = fit_check(20, "H7", "h7")
    rep = stack_up([
        {"nombre": "agujero", "nominal_mm": 20, "sentido": +1, "tol": {"fit": "H7"}},
        {"nombre": "eje", "nominal_mm": 20, "sentido": -1, "tol": {"fit": "h7"}},
    ])
    # juego en µm de fit_check ↔ intervalo de cierre en mm del stack-up
    assert rep["peor_caso"]["min_mm"] * 1000 == pytest.approx(fc["juego_min_um"], abs=1e-6)
    assert rep["peor_caso"]["max_mm"] * 1000 == pytest.approx(fc["juego_max_um"], abs=1e-6)
    assert rep["nominal_close_mm"] == 0.0


# ------------------------------------ peor caso falla, RSS cierra (el discriminante)
def test_three_plate_stack_wc_fails_rss_passes():
    """Ranura 25 menos 3 placas de 8 (todas en 6–30 mm → ISO 2768-m = ±0.2): el hueco
    nominal 1 mm. Con requisito [0.5, 1.5], el PEOR CASO se sale (0.2..1.8) pero el RSS
    cierra (0.6..1.4) — el reporte DISTINGUE ambos."""
    eslabones = [
        {"nombre": "ranura", "nominal_mm": 25, "sentido": +1, "tol": {"iso2768": "m"}},
        {"nombre": "placa 1", "nominal_mm": 8, "sentido": -1, "tol": {"iso2768": "m"}},
        {"nombre": "placa 2", "nominal_mm": 8, "sentido": -1, "tol": {"iso2768": "m"}},
        {"nombre": "placa 3", "nominal_mm": 8, "sentido": -1, "tol": {"iso2768": "m"}},
    ]
    rep = stack_up(eslabones, {"entre": [0.5, 1.5]})
    assert rep["nominal_close_mm"] == 1.0
    assert rep["peor_caso"]["min_mm"] == pytest.approx(0.2)
    assert rep["peor_caso"]["max_mm"] == pytest.approx(1.8)
    assert rep["ok_peor_caso"] is False           # peor caso NO cierra
    # RSS: media-tol 0.2 en 4 eslabones → √(4·0.04) = 0.4 alrededor de 1.0
    assert rep["rss"]["min_mm"] == pytest.approx(0.6)
    assert rep["rss"]["max_mm"] == pytest.approx(1.4)
    assert rep["ok_rss"] is True                  # RSS sí cierra


def test_pm_symmetric_and_lim_absolute():
    rep = stack_up([
        {"nombre": "a", "nominal_mm": 50, "sentido": +1, "tol": {"pm": 0.1}},
        {"nombre": "b", "nominal_mm": 50, "sentido": -1, "tol": {"lim": [49.9, 50.05]}},
    ])
    # cierre nominal 0; a ∈ [49.9,50.1], b ∈ [49.9,50.05] → a−b ∈ [-0.15, 0.2]
    assert rep["peor_caso"]["min_mm"] == pytest.approx(-0.15)
    assert rep["peor_caso"]["max_mm"] == pytest.approx(0.2)


def test_bad_tolerance_source_rejected():
    with pytest.raises(ValueError):
        stack_up([{"nombre": "x", "nominal_mm": 10, "sentido": 1, "tol": {"foo": 1}}])
    with pytest.raises(ValueError):
        stack_up([{"nombre": "x", "nominal_mm": 10, "sentido": 1,
                   "tol": {"pm": 0.1, "fit": "h7"}}])  # dos fuentes
    with pytest.raises(ValueError):
        stack_up([])  # cadena vacía


# ---------------------------------------------------- presupuesto de patrón de pernos
def test_bolt_pattern_budget():
    # M12 en barreno de paso Ø13.5: holgura radial (13.5−12)/2 = 0.75 mm por lado
    b = bolt_pattern_budget(13.5, 12.0, [0.3, 0.3])
    assert b["presupuesto_mm"] == pytest.approx(0.75)
    assert b["demanda_peor_caso_mm"] == pytest.approx(0.6)  # 0.3+0.3
    assert b["demanda_rss_mm"] == pytest.approx(math.sqrt(0.18), abs=1e-3)  # √0.18, redondeo 4dp
    assert b["ok_peor_caso"] is True
    # dos patrones muy dispersos NO cierran en peor caso
    b2 = bolt_pattern_budget(13.5, 12.0, [0.5, 0.5])
    assert b2["ok_peor_caso"] is False  # 1.0 > 0.75
    assert b2["ok_rss"] is True         # √0.5 ≈ 0.707 < 0.75
