"""La flexión del eje motriz con el vano CUADRADO (ruedas de banda modular de agujero cuadrado):
el «Ø40» del nombre es el muñón de la chumacera, no la sección que flecta (lavadora de bandejas,
2026-10-29: la regla daba 320 MPa con Ø40 y ERROR sin salida; el cuadrado 60 trabaja a ~56)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apolo.library.rules_comun import _CUADRADO_RE
from apolo.library.rules_faja_estructura import verificar_flexion_del_eje


def _ctx(conveyor):
    return SimpleNamespace(ancho=1205.0, checks=[], conveyor=conveyor, frame={"material": "acero"},
                           pull_n=2793.0, tambor_d=160.0)


def test_el_vano_cuadrado_flecta_como_cuadrado():
    redondo, cuadrado = _ctx({"eje_d": 40.0}), _ctx({"eje_d": 40.0, "eje_cuadrado": 60.0})
    verificar_flexion_del_eje(redondo)
    verificar_flexion_del_eje(cuadrado)
    r, c = redondo.checks[0], cuadrado.checks[0]
    assert r["estado"] == "error" and c["estado"] == "ok"
    m = 2 * 2793.0 * 1205.0 / 4
    assert f"{m / (60 ** 3 / 6):.0f} MPa" in c["detalle"] and "cuadrado 60" in c["detalle"]
    assert c["calc"]["formula"] == "σ = 6·(F·L/4) / a³"


def test_sin_cuadrado_la_regla_de_siempre():
    ctx = _ctx({"eje_d": 50.0})
    verificar_flexion_del_eje(ctx)
    assert ctx.checks[0]["calc"]["formula"] == "σ = 32·(F·L/4) / (π·d³)"


@pytest.mark.parametrize("nombre, a", [
    ("Eje motriz cuadrado 60 inox AISI 304, munones Ø40 h7", 60.0), ("Eje Cuadrado 38,1", 38.1)])
def test_el_nombre_dice_el_cuadrado(nombre, a):
    assert float(_CUADRADO_RE.search(nombre).group(1).replace(",", ".")) == a
