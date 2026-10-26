"""El presostato y la masa de los cilindros con su ficha leída (plan V8.9, § Presostato y masa por
carrera con ficha, 2026-10-26).

- El presostato `PRESOSTATO-1-10BAR` carga con la ficha Festo PEV-1/4-B (sin el SMC IS10 en su
  línea: no cumple), la histéresis típica del SMC IS3000 y sólo la sobrecarga a confirmar.
- La masa de un cilindro crece con la carrera: `weight` + `peso_por_mm_kg` × carrera (Festo
  DSBC-PPVA / DSNU-P-A). El caso de control del pendiente 9: Ø63 × 800 = 1,74 + 0,0062 × 800 =
  6,70 kg (la BOM daba 1,6).
- El vástago no se cuenta dos veces: la BOM compra el cilindro entero en la fila del cuerpo y las
  masas del conjunto reparten la ficha (cuerpo = total − móvil, vástago = móvil).
- Los máximos de carrera y la energía de impacto de las fichas citadas.
"""

from __future__ import annotations

import pytest

from apolo.doc import Document
from apolo.library.bom import bom_from_scene
from apolo.library.catalog import CATALOG
from apolo.library.cutlist import hardware_schedule, scene_weight_kg
from apolo.library.engineering.mass import feature_mass, scene_mass_properties
from apolo.library.peso_ficha import partes_de_cilindros, peso_de_ficha

# ref → (peso en carrera 0, peso por mm, masa móvil en carrera 0, móvil por mm), kg. Festo,
# fichas web «Technical data» leídas el 2026-10-26 (artículos en la cabecera del YAML).
FICHA = {
    "CIL-ISO15552-32": (0.465, 0.0027, 0.110, 0.0009),
    "CIL-ISO15552-40": (0.740, 0.0037, 0.205, 0.0016),
    "CIL-ISO15552-50": (1.190, 0.0056, 0.365, 0.0025),
    "CIL-ISO15552-63": (1.740, 0.0062, 0.430, 0.0025),
    "CIL-ISO6432-16": (0.0899, 0.00046, 0.023, 0.0002),
    "CIL-ISO6432-20": (0.1868, 0.00072, 0.044, 0.0004),
    "CIL-ISO6432-25": (0.238, 0.0011, 0.071, 0.0006),
}


# ── el presostato ────────────────────────────────────────────────────────────────────────────


def test_presostato_con_la_ficha_festo_pev():
    c = CATALOG["PRESOSTATO-1-10BAR"]
    s = c.specs
    assert c.weight == 0.194  # con su conector
    assert (s["rango_bar"], s["rango_ficha_bar"]) == ("1-10", "1-12")  # la función y lo que da la ficha
    assert (s["tension_contacto"], s["corriente_contacto_A"], s["envolvente"]) == ("250 VAC / 125 VDC", 5, "IP65")
    assert s["T_servicio_C"] == "-20…80"
    assert "IS10" not in s["linea_referencia"] and s["linea_referencia"] == "orden de Festo PEV-1/4-B (presostato con contacto conmutado)"
    assert "sobrecarga" in s["a_confirmar"]  # Festo no la publica para el PEV-1/4-B
    n, e = c.neumatico, c.electrico
    assert n.modelo["p_max_bar"] == 12.0 and n.modelo["histeresis_bar"] == 0.5 and n.a_confirmar == ()
    assert "IS3000" in n.fuente and "ajustable" in n.fuente  # la histéresis es TÍPICA, declarada
    assert (e.modelo["contacto_A"], e.modelo["contacto_V"]) == (5, 250)
    assert e.datos == {"T_max_C": 80.0} and e.a_confirmar == ()


# ── la masa por carrera ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref", sorted(FICHA))
def test_cada_cilindro_trae_su_peso_por_carrera_de_la_ficha(ref):
    w, por_mm, mb, mpm = FICHA[ref]
    c = CATALOG[ref]
    assert (c.weight, c.specs["peso_por_mm_kg"]) == (w, por_mm)
    m = c.neumatico.modelo
    assert (m["masa_movil_base_kg"], m["masa_movil_por_mm_kg"]) == (mb, mpm)
    assert "masa_movil_base_kg" not in c.neumatico.a_confirmar
    assert "peso en carrera 0" not in c.specs["a_confirmar"]
    assert peso_de_ficha(c, 100) == pytest.approx(w + por_mm * 100)
    assert peso_de_ficha(c, None) == w


def _cilindro(ref="CIL-ISO15552-63", carrera=800, **p):
    d = Document()
    cid = d.execute("create_pneumatic_cylinder", {"ref": ref, "carrera": carrera, "montaje": "ninguno", **p})
    return d, cid


def test_bom_del_ø63_por_800_pesa_lo_de_la_ficha():
    d, _ = _cilindro()
    (fila,) = [f for f in bom_from_scene(d.scene) if f["ref"] == "CIL-ISO15552-63"]
    assert fila["peso_unitario_kg"] == pytest.approx(1.74 + 0.0062 * 800) == 6.70  # la BOM daba 1,6
    assert fila["incluye"] == ["Cilindro · Vástago"]
    assert not any("Vástago" in f["descripcion"] for f in bom_from_scene(d.scene))


def test_el_vastago_no_se_cuenta_dos_veces():
    d, cid = _cilindro()
    cuerpo, vastago = f"{cid}_cuerpo", f"{cid}_vastago"
    movil = 0.430 + 0.0025 * 800
    assert partes_de_cilindros(d.scene) == pytest.approx({cuerpo: 6.70 - movil, vastago: movil})
    mp = scene_mass_properties(d.scene)
    masas = {p["id"]: (p["masa_kg"], p["fuente"]) for p in mp["piezas"]}
    assert masas[cuerpo] == (pytest.approx(6.70 - movil), "catálogo")
    assert masas[vastago] == (pytest.approx(movil), "catálogo")  # antes: su volumen, sumado al total
    assert mp["total"]["masa_kg"] == pytest.approx(6.70)
    assert scene_weight_kg(d.scene) == pytest.approx(6.70)
    # sin el reparto (una pieza suelta), el cuerpo es el cilindro entero de la ficha
    assert feature_mass(d.scene[cuerpo])["masa_kg"] == pytest.approx(6.70)
    # la cédula de compra, como la BOM: por ref + carrera
    (h,) = [r for r in hardware_schedule(d.scene) if r["ref"] == "CIL-ISO15552-63"]
    assert h["peso_ud_kg"] == pytest.approx(6.70) and "carrera 800 mm" in h["nombre"]


def test_con_accesorios_el_resto_sigue_pesando_por_volumen():
    d, cid = _cilindro("CIL-ISO15552-32", 300, montaje="pies")
    mp = {p["id"]: p for p in scene_mass_properties(d.scene)["piezas"]}
    assert mp[f"{cid}_pie_delantero"]["fuente"] == "volumen"
    cil = mp[f"{cid}_cuerpo"]["masa_kg"] + mp[f"{cid}_vastago"]["masa_kg"]
    assert cil == pytest.approx(0.465 + 0.0027 * 300, abs=1e-3)


# ── carreras y amortiguación de las fichas citadas ───────────────────────────────────────────


def test_carrera_maxima_y_energia_de_las_fichas():
    m = {r: CATALOG[r].neumatico.modelo for r in FICHA}
    # SMC C96 (pág. PDF 5): Ø32 hasta 1000 mm, Ø40–63 hasta 1900; CP96 Ø63 hasta 2000
    assert [m[f"CIL-ISO15552-{D}"]["carrera_max_mm"] for D in (32, 40, 50, 63)] == [1000, 1900, 1900, 2000]
    # Festo DSNU-P-A: energía de impacto admisible 0,15 / 0,2 / 0,3 J (el 0,4 era el tope del SMC C85)
    assert [m[f"CIL-ISO6432-{D}"]["E_amortiguacion_J"] for D in (16, 20, 25)] == [0.15, 0.2, 0.3]
    assert all("E_amortiguacion_J" not in CATALOG[r].neumatico.a_confirmar for r in FICHA)
    with pytest.raises(Exception, match="fuera del rango de su ficha"):
        _cilindro("CIL-ISO15552-32", 1200)
