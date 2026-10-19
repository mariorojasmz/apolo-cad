"""Secciones por familia del catálogo (`library/engineering/secciones.py`), plan flecha-de-bastidor F1.

Tres verificaciones independientes:
  - HSS contra las tablas del AISC Steel Construction Manual (dimensiones en pulgadas exactas);
  - tablas de norma (EN 10056-1, DIN 1026-1, EN 10365) contra sí mismas (W = I/c con el
    centroide publicado) y contra la geometría prismática (cazan un error de transcripción:
    los acuerdos mueven I unos pocos %, no decenas);
  - cada variante de perfil del catálogo resuelve a su fila de tabla o a HSS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from apolo.library.engineering.secciones import (
    _ANGULOS,
    _IPE,
    _UPN,
    SIN_SECCION,
    rects_angulo,
    rects_canal,
    rects_viga_i,
    seccion_catalogo,
    seccion_hss_rect,
    seccion_hss_redondo,
    seccion_rect_hueca,
    seccion_rectangulos,
    seccion_tubo_redondo,
)
from apolo.library.structural import rect_tube_inertia_mm4

IN = 25.4
DATA = Path(__file__).resolve().parents[1] / "core" / "apolo" / "library" / "data"


# ── HSS (ASTM A500 / AISC) ────────────────────────────────────────────────────


@pytest.mark.parametrize("b, t, area_in2, i_in4, s_in3", [
    (2.0, 0.125, 0.840, 0.486, 0.486),
    (3.0, 0.1875, 1.89, 2.46, 1.64),
    (4.0, 0.25, 3.37, 7.80, 3.90),
    (6.0, 0.25, 5.24, 28.6, 9.54),
])
def test_hss_cuadrado_contra_aisc(b, t, area_in2, i_in4, s_in3):
    s = seccion_hss_rect(b * IN, b * IN, t * IN)
    assert s.area_mm2 / IN**2 == pytest.approx(area_in2, rel=0.01)
    assert s.i_x_mm4 / IN**4 == pytest.approx(i_in4, rel=0.01)
    assert s.w_x_mm3 / IN**3 == pytest.approx(s_in3, rel=0.01)
    assert s.i_y_mm4 == pytest.approx(s.i_x_mm4) and s.fuente == "hss"


def test_tubo_aristas_vivas_igual_a_structural():
    s = seccion_rect_hueca(40, 80, 3)
    assert s.i_x_mm4 == pytest.approx(rect_tube_inertia_mm4(40, 80, 3), rel=1e-12)
    assert s.i_y_mm4 == pytest.approx(rect_tube_inertia_mm4(80, 40, 3), rel=1e-12)
    assert s.area_mm2 == pytest.approx(40 * 80 - 34 * 74)
    assert seccion_rect_hueca(40, 80, 50).i_x_mm4 == pytest.approx(40 * 80**3 / 12)  # macizo


def test_tubo_redondo_y_hss_redondo():
    s = seccion_tubo_redondo(50.8, 3.0)
    assert s.i_x_mm4 == pytest.approx(3.141592653589793 / 64 * (50.8**4 - 44.8**4), rel=1e-12)
    assert s.w_x_mm3 == pytest.approx(s.i_x_mm4 / 25.4)
    # HSS4.000×0.250 (AISC: t_des = 0.233 in) → I ≈ 4.91 in⁴
    assert seccion_hss_redondo(4 * IN, 0.25 * IN).i_x_mm4 / IN**4 == pytest.approx(4.91, rel=0.01)


def test_ejes_locales_del_builder():
    """El canto es la medida en Y: el tubo 4"×2" (width 101.6 en X) es DÉBIL respecto a X."""
    tubo = seccion_catalogo("rect_tube", {"width": 101.6, "height": 50.8, "wall": 4.8})
    assert tubo.i_x_mm4 < tubo.i_y_mm4
    upn = seccion_catalogo("channel", {"h": 100, "b": 50, "tw": 6, "tf": 8.5})
    assert upn.i_x_mm4 == pytest.approx(206e4) and upn.i_y_mm4 == pytest.approx(29.3e4)


# ── Tablas de norma ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("dims, fila", sorted(_ANGULOS.items()))
def test_tabla_angulo(dims, fila):
    lado, t = dims
    assert fila["W"] == pytest.approx(fila["I"] / (lado / 10 - fila["e"]), rel=0.015)
    geo = seccion_rectangulos(rects_angulo(lado, t))
    assert fila["I"] * 1e4 == pytest.approx(geo.i_x_mm4, rel=0.07)
    assert fila["A"] * 100 == pytest.approx(geo.area_mm2, rel=0.03)
    assert fila["Iv"] * 1e4 == pytest.approx(geo.i_min_mm4, rel=0.07)
    assert fila["Iv"] < fila["I"]


@pytest.mark.parametrize("h, fila", sorted(_UPN.items()))
def test_tabla_upn(h, fila):
    b, tw, tf = fila["dims"]
    assert fila["Wy"] == pytest.approx(fila["Iy"] / (h / 20), rel=0.015)
    assert fila["Wz"] == pytest.approx(fila["Iz"] / (b / 10 - fila["e"]), rel=0.015)
    geo = seccion_rectangulos(rects_canal(h, b, tw, tf))
    assert fila["Iy"] * 1e4 == pytest.approx(geo.i_x_mm4, rel=0.07)
    # eje débil: el ala cónica (8 %) es más delgada en la punta → la tabla queda 9-14 % bajo el
    # prismático con tf medio (medido: 0.867-0.890 en toda la serie, sin saltos)
    assert 0.85 * geo.i_y_mm4 <= fila["Iz"] * 1e4 <= 0.92 * geo.i_y_mm4
    assert fila["A"] * 100 == pytest.approx(geo.area_mm2, rel=0.06)


@pytest.mark.parametrize("h, fila", sorted(_IPE.items()))
def test_tabla_ipe(h, fila):
    b, tw, tf = fila["dims"]
    assert fila["Wy"] == pytest.approx(fila["Iy"] / (h / 20), rel=0.015)
    assert fila["Wz"] == pytest.approx(fila["Iz"] / (b / 20), rel=0.015)
    geo = seccion_rectangulos(rects_viga_i(h, b, tw, tf))
    # sin el acuerdo de raíz la geometría queda POR DEBAJO (conservadora)
    assert geo.i_x_mm4 <= fila["Iy"] * 1e4 <= 1.07 * geo.i_x_mm4
    assert fila["A"] * 100 == pytest.approx(geo.area_mm2, rel=0.06)


def test_geometria_prismatica_por_otro_metodo():
    """Fuera de tabla → geometría; se compara con las fórmulas cerradas de cada forma."""
    lado, t = 75.0, 7.0  # L 75×7 no está en la tabla del catálogo
    s = seccion_catalogo("angle", {"leg": lado, "t": t})
    a = 2 * lado * t - t * t
    e = (lado * t * lado / 2 + (lado - t) * t * t / 2) / a
    i = t * lado**3 / 3 + (lado - t) * t**3 / 3 - a * e * e
    assert s.fuente == "geometría" and "sin acuerdos" in s.norma
    assert s.i_x_mm4 == pytest.approx(i, rel=1e-12)
    assert s.w_x_mm3 == pytest.approx(i / (lado - e), rel=1e-12)
    h, b, tw, tf = 210.0, 100.0, 6.0, 9.0
    s = seccion_catalogo("i_beam", {"h": h, "b": b, "tw": tw, "tf": tf})
    assert s.i_x_mm4 == pytest.approx((b * h**3 - (b - tw) * (h - 2 * tf) ** 3) / 12, rel=1e-12)
    assert s.i_min_mm4 == pytest.approx(s.i_y_mm4)


# ── Cobertura del catálogo ────────────────────────────────────────────────────


def _familias():
    for archivo in ("13_perfiles_abiertos.yaml", "15_tubos_estructurales.yaml", "12_tubos_circulares.yaml"):
        datos = yaml.safe_load((DATA / archivo).read_text(encoding="utf-8"))
        for fam in datos["families"]:
            for v in fam["variants"]:
                yield fam["builder"], v["ref"], {k: v[k] for k in fam["param_keys"]}


@pytest.mark.parametrize("builder, ref, params", list(_familias()))
def test_cada_perfil_del_catalogo_tiene_seccion(builder, ref, params):
    s = seccion_catalogo(builder, params)
    esperada = "hss" if builder in ("rect_tube", "round_tube") else "tabla"
    assert s is not None and s.fuente == esperada, ref
    assert s.i_min_mm4 <= min(s.i_x_mm4, s.i_y_mm4) + 1e-6


def test_familias_sin_seccion():
    assert seccion_catalogo("profile", {"size": "40x40"}) is None
    assert "fabricante" in SIN_SECCION["profile"]
    assert seccion_catalogo("roller", {"diameter": 50}) is None
    eje = seccion_catalogo("cylinder", {"diameter": 35})
    assert eje.i_x_mm4 == pytest.approx(3.141592653589793 * 35**4 / 64)
