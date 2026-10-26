"""Catálogo neumático genérico (plan V8.9 D16, F1a): cada ref carga con su ficha y su fuente, y
las cotas transcritas coinciden con la fuente citada en el YAML."""

from __future__ import annotations

import pytest

from apolo.library.catalog import CATALOG, CATEGORIES, build_component, catalog_payload, refs_in_category

NUEVAS = {
    "cilindros_neumaticos": ["CIL-ISO15552-32", "CIL-ISO15552-40", "CIL-ISO15552-50", "CIL-ISO15552-63",
                             "CIL-ISO6432-16", "CIL-ISO6432-20", "CIL-ISO6432-25"],
    "valvulas_neumaticas": [f"VAL-{t}-{g}" for g in ("G18", "G14")
                            for t in ("52-MONO", "52-BI", "53-CC", "53-CE", "53-CP", "32-NC")],
    "aire_comprimido": ["FR-G14", "FR-G12", "CORTE-ESC-G14", "CORTE-ESC-G12",
                        "TUBO-PU-4", "TUBO-PU-6", "TUBO-PU-8", "TUBO-PU-10"],
}
TODAS = [r for refs in NUEVAS.values() for r in refs]

# Cotas transcritas, con su fuente (la cabecera de 130_cilindros_neumaticos.yaml):
# Ø pistón → (Ø vástago, rosca del vástago, puertos, TG, cuerpo en carrera 0, E admisible en J)
ISO15552 = {  # [F1] SMC C96*-OM0001Q · [F2] hojas SMC · [F3] AVENTICS 6907744 · [F4] Flowtech TS3017
    32: (12, "M10x1.25", "G1/8", 32.5, 94, 2.3),
    40: (16, "M12x1.25", "G1/4", 38, 105, 3.6),
    50: (20, "M16x1.5", "G1/4", 46.5, 106, 6.1),
    63: (20, "M16x1.5", "G3/8", 56.5, 121, 11.4),
}
ISO6432 = {  # [F5] Hydraquip TS10287: vástago, rosca, nariz, puertos
    16: (6, "M6", "M16x1.5", "M5"),
    20: (8, "M8", "M22x1.5", "G1/8"),
    25: (10, "M10x1.25", "M22x1.5", "G1/8"),
}


#: V8.9 F7b (defecto 12): reguladores de caudal en línea, silenciadores y racores (sólo BOM)
F7B = ["REG-CAUDAL-L-6", "REG-CAUDAL-L-8", "REG-CAUDAL-L-10", "SIL-G18", "SIL-G14", "SIL-G12"]
RACORES = ["RACOR-M5-4", "RACOR-G18-4", "RACOR-M5-6", "RACOR-G18-6", "RACOR-G14-6", "RACOR-G18-8",
           "RACOR-G14-8", "RACOR-G38-8", "RACOR-G14-10", "RACOR-G38-10", "RACOR-G12-10"]
#: V8.9 F8: el presostato (`tests/test_v89_f8_presostato.py` revisa sus dos fichas)
F8 = ["PRESOSTATO-1-10BAR"]


def test_categorias_al_final_con_sus_refs():
    assert CATEGORIES[-3:] == list(NUEVAS)  # al final: no reordenan la UI
    for categoria, refs in NUEVAS.items():
        extra = F7B + RACORES + F8 if categoria == "aire_comprimido" else []
        assert sorted(refs_in_category(categoria)) == sorted(refs + extra)


@pytest.mark.parametrize("ref", F7B)
def test_los_accesorios_de_f7b_cargan_con_su_ficha(ref):
    f = CATALOG[ref].neumatico
    assert f is not None and f.fuente.strip() and f.funcion == "RZ" and f.caudal.C > 0
    assert f.a_confirmar  # sin ficha de proveedor leída: todo a confirmar
    assert CATALOG[ref].specs["cost"] > 0


@pytest.mark.parametrize("ref", RACORES)
def test_cada_racor_declara_su_rosca_y_su_tubo(ref):
    s = CATALOG[ref].specs
    _, rosca, tubo = ref.split("-")
    assert s["racor_rosca"] == {"M5": "M5", "G18": "G1/8", "G14": "G1/4", "G38": "G3/8", "G12": "G1/2"}[rosca]
    assert s["racor_tubo_mm"] == float(tubo) and s["cost"] > 0 and CATALOG[ref].neumatico is None


@pytest.mark.parametrize("ref", TODAS)
def test_cada_ref_carga_con_su_ficha_y_su_fuente(ref):
    c = CATALOG[ref]
    f = c.neumatico
    assert f is not None and f.fuente.strip(), ref
    s = c.specs
    assert s["linea_referencia"].startswith("orden de "), ref  # una ref es un EJEMPLO
    assert s["cotas_verificadas"] is False
    assert (s.get("cost_por_m") if c.cuttable else s.get("cost")), ref
    assert "Verificar con el proveedor" in c.description
    # F1b: una electroválvula lleva sus bobinas en `electrico:` (A1/A2 o 14A1…12A2); lo demás, no
    assert (c.electrico is not None) == bool(f.modelo.get("bobinas")), ref
    build_component(ref, 500 if c.cuttable else None)


def test_designaciones_de_dos_letras():
    for ref in TODAS:
        f = CATALOG[ref].neumatico
        esperada = {"cilindro": "MM", "valvula": "QM", "valvula_corte": "QM", "frl": "AZ", None: "WP"}[f.tipo]
        assert f.funcion == esperada, ref


@pytest.mark.parametrize("D", sorted(ISO15552))
def test_iso15552_transcrito_de_su_fuente(D):
    d, kk, puerto, tg, cuerpo, energia = ISO15552[D]
    c = CATALOG[f"CIL-ISO15552-{D}"]
    m = c.neumatico.modelo
    assert (m["D_mm"], m["d_mm"], m["E_amortiguacion_J"]) == (D, d, energia)
    assert (c.specs["rosca_vastago"], c.specs["rosca_puertos"], c.specs["TG_mm"]) == (kk, puerto, tg)
    assert c.specs["largo_cuerpo_mm"] == cuerpo == c.params["C"]  # el builder de la F2 lo lee
    assert (c.params["D"], c.params["d"], c.params["TG"]) == (D, d, tg)
    assert {p.rosca for p in c.neumatico.puertos} == {puerto}
    assert (m["p_min_bar"], m["p_max_bar"]) == (0.5, 10)  # SMC C96: 0,05–1,0 MPa
    assert m["masa_movil_por_mm_kg"] == pytest.approx(3.14159 * d ** 2 / 4 * 7.85e-6, rel=1e-3)


@pytest.mark.parametrize("D", sorted(ISO6432))
def test_iso6432_transcrito_de_su_fuente(D):
    d, kk, nariz, puerto = ISO6432[D]
    c = CATALOG[f"CIL-ISO6432-{D}"]
    assert (c.neumatico.modelo["d_mm"], c.specs["rosca_vastago"], c.specs["rosca_nariz"]) == (d, kk, nariz)
    assert {p.rosca for p in c.neumatico.puertos} == {puerto}
    assert (c.neumatico.modelo["carrera_min_mm"], c.neumatico.modelo["carrera_max_mm"]) == (10, 320)


def test_valvulas_iso5599_3_y_su_mando():
    for ref in NUEVAS["valvulas_neumaticas"]:
        f = CATALOG[ref].neumatico
        roles = {p.id: p.rol for p in f.puertos}
        assert roles["1"] == "alimentacion" and roles["2"] == "trabajo" and roles["3"] == "escape"
        if f.modelo["vias"] == 5:
            assert roles["4"] == "trabajo" and roles["5"] == "escape"
        dos = f.modelo["mando"] != "monoestable"
        assert f.modelo["bobinas"] == (["14", "12"] if dos else ["14"] if f.modelo["vias"] == 5 else ["12"])
        assert f.caudal.C > 0 and "caudal.b" in f.a_confirmar  # b = 0,3 es hipótesis declarada
    # la monoestable G1/8 sale del Qn de su fuente (Festo VUVG-L14: 680 L/min de 6 a 5 bar)
    v = CATALOG["VAL-52-MONO-G18"].neumatico
    assert v.caudal.origen == "convertido de Qn = 680 L/min ANR (6→5 bar)"
    assert (v.modelo["t_on_ms"], v.modelo["t_off_ms"], v.modelo["p_min_bar"], v.modelo["p_max_bar"]) == (14, 22, 2.5, 8)
    # la G1/4 trae C de su ficha (SMC VF3130) y el escape aparte
    g14 = CATALOG["VAL-52-MONO-G14"].neumatico
    assert (g14.caudal.C, g14.escape.C) == (4.0, 3.1)


def test_frl_y_corte():
    for ref in ("FR-G14", "FR-G12"):
        f = CATALOG[ref].neumatico
        assert f.ajustes == {"p_regulada_bar": (0.5, 8.5)}  # lo fija el instalador
        assert f.modelo["lubricador"] is False
    for ref in ("CORTE-ESC-G14", "CORTE-ESC-G12"):
        m = CATALOG[ref].neumatico.modelo
        assert m["con_escape"] and m["bloqueable"] and m["accionamiento"] == "manual"


def test_tubos_por_metro():
    for od, di in ((4, 2.5), (6, 4), (8, 5), (10, 6.5)):
        c = CATALOG[f"TUBO-PU-{od}"]
        assert c.cuttable and c.neumatico.tubo.D_ext_mm == od and c.neumatico.tubo.D_int_mm == di
        assert c.params == {"od": od, "wall": (od - di) / 2}
        # peso por metro con PU ≈ 1,2 g/cm³: π/4·(od² − di²) mm² · 1 m · 1,2e-6 kg/mm³ · 1000
        assert c.weight == pytest.approx(3.14159 / 4 * (od ** 2 - di ** 2) * 1.2e-3, rel=0.01)


def test_payload_del_catalogo_lleva_la_ficha():
    p = {x["ref"]: x for x in catalog_payload("valvulas_neumaticas")}
    assert p["VAL-52-MONO-G18"]["neumatico"]["caudal"]["C"] == pytest.approx(2.6715, abs=1e-4)
    assert "neumatico" not in catalog_payload("rodamientos")[0]
