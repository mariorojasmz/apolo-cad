"""Radios de acuerdo de norma en el catálogo de perfiles abiertos (plan perfiles-con-acuerdo,
F1/D1): r1/r2 por variante contra las tablas citadas, la zona plana que derivan contra la
altura recta del alma `d` publicada, y la validación del loader."""

import math
import os

import pytest

from apolo.library.acuerdos import inicio_zona_plana_alma, validar_acuerdo, zona_plana_ala_angulo
from apolo.library.catalog import CATALOG, build_component, refs_in_category
from apolo.library.loader import load_catalog

# DIN 1026-1 (UPN): h, b, tw(s), tf(t), r1, r2, d (altura recta del alma). Pendiente 8 %.
UPN = {
    "UPN-80": (80, 45, 6, 8, 8, 4, 47),
    "UPN-100": (100, 50, 6, 8.5, 8.5, 4.5, 64),
    "UPN-120": (120, 55, 7, 9, 9, 4.5, 82),
    "UPN-140": (140, 60, 7, 10, 10, 5, 98),
    "UPN-160": (160, 65, 7.5, 10.5, 10.5, 5.5, 115),
    "UPN-180": (180, 70, 8, 11, 11, 5.5, 133),
    "UPN-200": (200, 75, 8.5, 11.5, 11.5, 6, 151),
}
# EN 10365 (IPE): h, b, tw, tf, r, d. Alas paralelas, un solo radio (sin radio de punta).
IPE = {
    "IPE-80": (80, 46, 3.8, 5.2, 5, 59.6),
    "IPE-100": (100, 55, 4.1, 5.7, 7, 74.6),
    "IPE-120": (120, 64, 4.4, 6.3, 7, 93.4),
    "IPE-140": (140, 73, 4.7, 6.9, 7, 112.2),
    "IPE-160": (160, 82, 5.0, 7.4, 9, 127.2),
    "IPE-180": (180, 91, 5.3, 8.0, 9, 146.0),
    "IPE-200": (200, 100, 5.6, 8.5, 12, 159.0),
}
# EN 10056-1 (ángulos de lados iguales): leg, t, r1 (raíz), r2 (punta = r1/2).
ANG = {
    "ANG-25X3": (25, 3, 3.5, 1.75),
    "ANG-30X3": (30, 3, 5, 2.5),
    "ANG-40X4": (40, 4, 6, 3),
    "ANG-50X5": (50, 5, 7, 3.5),
    "ANG-60X6": (60, 6, 8, 4),
    "ANG-75X6": (75, 6, 9, 4.5),
    "ANG-80X8": (80, 8, 10, 5),
    "ANG-100X10": (100, 10, 12, 6),
}


def test_todas_las_variantes_tienen_r1_de_norma():
    refs = set(refs_in_category("perfiles_abiertos"))
    assert refs == set(UPN) | set(IPE) | set(ANG)  # ninguna variante sin dato de norma
    for ref, (h, b, tw, tf, r1, r2, _d) in UPN.items():
        s = CATALOG[ref].specs
        assert (s["h"], s["b"], s["tw"], s["tf"], s["r1"], s["r2"]) == (h, b, tw, tf, r1, r2), ref
        assert s["pendiente_ala"] == 0.08
    for ref, (h, b, tw, tf, r, _d) in IPE.items():
        s = CATALOG[ref].specs
        assert (s["h"], s["b"], s["tw"], s["tf"], s["r1"]) == (h, b, tw, tf, r), ref
        assert "r2" not in s and not s.get("pendiente_ala")
    for ref, (leg, t, r1, r2) in ANG.items():
        s = CATALOG[ref].specs
        assert (s["leg"], s["t"], s["r1"], s["r2"]) == (leg, t, r1, r2), ref


@pytest.mark.parametrize("ref", sorted(UPN))
def test_upn_zona_plana_reproduce_d_publicada(ref):
    """h − 2·s (acuerdo + conicidad 8 % con tf a b/2) da la `d` de DIN 1026-1 a ±1 mm: ancla
    que caza un r1 o una pendiente mal copiados."""
    h, *_, d = UPN[ref]
    s = inicio_zona_plana_alma(CATALOG[ref].specs)
    assert abs((h - 2 * s) - d) <= 1.0, (ref, h - 2 * s, d)


@pytest.mark.parametrize("ref", sorted(IPE))
def test_ipe_zona_plana_es_d_exacta(ref):
    h, *_, d = IPE[ref]
    s = inicio_zona_plana_alma(CATALOG[ref].specs)
    assert math.isclose(h - 2 * s, d, abs_tol=0.05), (ref, h - 2 * s, d)


def test_upn100_zona_plana_empieza_a_18mm():
    """El caso de la piloto (proyecto 2): ~18 mm del canto, no los 8.5 del ala prismática."""
    assert inicio_zona_plana_alma(CATALOG["UPN-100"].specs) == pytest.approx(17.87, abs=0.05)


def test_angulo_zona_plana_del_ala():
    assert zona_plana_ala_angulo(CATALOG["ANG-50X5"].specs) == (12.0, 46.5)
    for ref in ANG:
        lo, hi = zona_plana_ala_angulo(CATALOG[ref].specs)
        assert 0 < lo < hi < CATALOG[ref].specs["leg"]


def test_r1_no_cambia_la_geometria():
    """El builder no lee r1/r2: el perfil sigue prismático (sin bump de GEOM_CACHE_EPOCH)."""
    shp, _ = build_component("UPN-100", 1000)
    h, b, tw, tf = 100, 50, 6, 8.5
    assert math.isclose(shp.volume, (h * tw + 2 * tf * (b - tw)) * 1000, rel_tol=1e-9)


@pytest.mark.parametrize("variante, error", [
    ("{ref: X-1, h: 100, b: 50, tw: 6, tf: 8.5, r1: -1}", "≥ 0"),
    ("{ref: X-1, h: 100, b: 50, tw: 6, tf: 8.5, r1: 'ocho'}", "≥ 0"),
    ("{ref: X-1, h: 100, b: 50, tw: 6, tf: 8.5, r1: 45}", "zona plana"),
    ("{ref: X-1, h: 100, b: 50, tw: 6, tf: 8.5, r2: 4}", "sin r1"),
    ("{ref: X-1, h: 100, b: 50, tw: 6, tf: 8.5, r1: 8, pendiente_ala: 8}", "fracción"),
])
def test_loader_rechaza_acuerdo_invalido(tmp_path, variante, error):
    (tmp_path / "x.yaml").write_text(
        "category: perfiles_abiertos\nfamilies:\n  - builder: channel\n"
        "    name_tpl: 'Canal {ref}'\n    param_keys: [h, b, tw, tf]\n    weight: 1\n"
        f"    variants:\n      - {variante}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        load_catalog(os.fspath(tmp_path))


def test_validar_acuerdo_angulo_sin_zona_plana():
    with pytest.raises(ValueError, match="ala no tiene zona plana"):
        validar_acuerdo({"leg": 20, "t": 3, "r1": 12, "r2": 6}, "ANG-X")
    validar_acuerdo({"leg": 50, "t": 5, "r1": 7, "r2": 3.5}, "ANG-50X5")  # sano: no lanza
    validar_acuerdo({"od": 30}, "TUBO")  # sin claves de acuerdo: no aplica
