"""Ficha neumática (plan V8.9 D2, F1a): el bloque `neumatico:` se valida al cargar y un bloque
incompleto NO carga, con la corrección en el mensaje."""

from __future__ import annotations

import copy

import pytest
import yaml

from apolo.library.loader import load_catalog
from apolo.library.neumatica.ficha import ficha_payload, parse_ficha_neumatica

CILINDRO = {
    "funcion": "MM", "simbolo": "cilindro_doble_efecto", "fuente": "ficha de prueba",
    "puertos": [{"id": "A", "rol": "trabajo", "rosca": "G1/8"}, {"id": "B", "rol": "trabajo", "rosca": "G1/8"}],
    "modelo": {"tipo": "cilindro", "norma": "ISO 15552", "efecto": "doble", "D_mm": 32, "d_mm": 12,
               "carrera_min_mm": 10, "carrera_max_mm": 500, "V_muerto_A_cm3": 4, "V_muerto_B_cm3": 3.5,
               "masa_movil_base_kg": 0.1, "masa_movil_por_mm_kg": 0.0009, "friccion_pct": 10,
               "amortiguacion": "neumatica", "E_amortiguacion_J": 2.3, "p_min_bar": 0.5, "p_max_bar": 10},
    "a_confirmar": ["friccion_pct"],
}
_P5 = [{"id": i, "rol": r, "rosca": "G1/8"} for i, r in
       (("1", "alimentacion"), ("2", "trabajo"), ("3", "escape"), ("4", "trabajo"), ("5", "escape"))]
VALVULA = {
    "funcion": "QM", "simbolo": "valvula_5_2_monoestable", "fuente": "ficha de prueba", "puertos": _P5,
    "modelo": {"tipo": "valvula", "vias": 5, "posiciones": 2, "mando": "monoestable",
               "accionamiento": "electrico", "bobinas": ["14"], "tension_bobina": "24 VDC", "manual": True,
               "t_on_ms": 14, "t_off_ms": 22, "p_min_bar": 2.5, "p_max_bar": 8,
               "caudal": {"C": 2.5, "b": 0.3}},
}
FRL = {
    "funcion": "AZ", "simbolo": "frl", "fuente": "ficha de prueba",
    "puertos": [{"id": "1", "rol": "entrada", "rosca": "G1/4"}, {"id": "2", "rol": "salida", "rosca": "G1/4"}],
    "modelo": {"tipo": "frl", "filtro_um": 5, "lubricador": False, "p_max_bar": 10,
               "p_regulada_bar": [0.5, 8.5], "caudal": {"Qn_l_min": 750, "referencia": "ANR",
                                                        "p1_bar": 6, "p2_bar": 5, "b": 0.3}},
}


def _con(base: dict, ruta: str, valor) -> dict:
    """Copia de `base` con `ruta` («modelo.D_mm») = valor; valor None BORRA la clave."""
    d = copy.deepcopy(base)
    *camino, ultima = ruta.split(".")
    nodo = d
    for k in camino:
        nodo = nodo[k]
    if valor is None:
        del nodo[ultima]
    else:
        nodo[ultima] = valor
    return d


def test_fichas_completas_cargan():
    c = parse_ficha_neumatica(CILINDRO, "C")
    assert c.tipo == "cilindro" and c.ids_puertos == ("A", "B") and c.a_confirmar == ("friccion_pct",)
    v = parse_ficha_neumatica(VALVULA, "V")
    assert v.caudal.C == 2.5 and v.caudal.origen.startswith("C y b de la ficha")
    assert any("m = 0,5" in h for h in v.caudal.hipotesis)  # m supuesto, declarado
    f = parse_ficha_neumatica(FRL, "F")
    assert f.ajustes == {"p_regulada_bar": (0.5, 8.5)}
    assert f.caudal.origen.startswith("convertido de Qn = 750 L/min ANR")
    assert ficha_payload(f)["ajustes"] == {"p_regulada_bar": [0.5, 8.5]}
    assert parse_ficha_neumatica(None, "X") is None


@pytest.mark.parametrize("base, ruta, valor, mensaje", [
    (CILINDRO, "fuente", None, r"neumatico\.fuente: falta"),
    (CILINDRO, "modelo.E_amortiguacion_J", None, r"E_amortiguacion_J: falta \(energía cinética admisible.*a_confirmar"),
    (CILINDRO, "modelo.friccion_pct", None, "UNA fricción"),
    (CILINDRO, "modelo.d_mm", 40, "va dentro del pistón"),
    (CILINDRO, "modelo.efecto", "triple", "«triple» no es válido"),
    (CILINDRO, "modelo.D_diam", 32, "clave desconocida «D_diam»"),
    (CILINDRO, "funcion", "M", "la designación de un cilindro es «MM»"),
    (CILINDRO, "puertos", [{"id": "A", "rol": "trabajo", "rosca": "G1/8"}], "falta el puerto «B»"),
    (CILINDRO, "a_confirmar", ["V_muerto_C_cm3"], "no es un dato de esta ficha"),
    (VALVULA, "modelo.caudal", None, r"caudal: falta"),
    (VALVULA, "modelo.caudal.b", None, "necesita su `b`"),
    (VALVULA, "modelo.caudal", {"C": 2.5, "Kv": 1, "b": 0.3}, "UNA forma"),
    (VALVULA, "modelo.caudal.b", 1.2, r"\[0, 1\)"),
    (VALVULA, "modelo.bobinas", ["14", "12"], r"lleva bobina\(s\) en \['14'\]"),
    (VALVULA, "modelo.tension_bobina", None, "tension_bobina: falta"),
    (VALVULA, "modelo.mando", "centro_cerrado", "no es «centro_cerrado»"),
    (VALVULA, "puertos", _P5[:4], "falta el puerto «5»"),
    (VALVULA, "puertos", [dict(p, rol="trabajo") if p["id"] == "3" else p for p in _P5], "«3» es de rol «escape»"),
    (VALVULA, "puertos", _P5 + [{"id": "7", "rol": "escape", "rosca": "G1/8"}], "no es una vía de ISO 5599-3"),
    (VALVULA, "puertos", [dict(p, rosca="1/8") if p["id"] == "1" else p for p in _P5], "se espera una rosca"),
    (FRL, "modelo.p_regulada_bar", 6, "AJUSTE que fija el instalador"),
    (FRL, "modelo.caudal.referencia", "SCFM", "opciones ANR, DIN1343"),
    (FRL, "modelo.caudal.p2_bar", 7, "p1_bar > p2_bar"),
])
def test_bloque_incompleto_o_mal_escrito_no_carga(base, ruta, valor, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        parse_ficha_neumatica(_con(base, ruta, valor), "REF-X")


def test_3_2_lleva_reposo_y_bobina_12():
    tres = _con(VALVULA, "puertos", _P5[:3])
    tres["modelo"].update(vias=3, bobinas=["12"])
    with pytest.raises(ValueError, match="reposo: falta"):
        parse_ficha_neumatica(tres, "V32")
    tres["modelo"]["reposo"] = "NC"
    assert parse_ficha_neumatica(tres, "V32").modelo["reposo"] == "NC"
    tres["modelo"]["bobinas"] = ["14"]
    with pytest.raises(ValueError, match=r"\['12'\]"):
        parse_ficha_neumatica(tres, "V32")


def test_tubo_por_metro():
    tubo = {"funcion": "WP", "simbolo": "tubo", "fuente": "TU0604",
            "tubo": {"D_ext_mm": 6, "D_int_mm": 4, "material": "PU", "p_max_bar": 8, "radio_min_mm": 15},
            "a_confirmar": ["tubo.p_max_bar"]}
    t = parse_ficha_neumatica(tubo, "T")
    assert t.tubo.D_int_mm == 4 and t.tipo is None and t.puertos == ()
    with pytest.raises(ValueError, match="Ø interior va dentro"):
        parse_ficha_neumatica(_con(tubo, "tubo.D_int_mm", 7), "T")
    with pytest.raises(ValueError, match="uno de los dos"):
        parse_ficha_neumatica(dict(tubo, modelo=CILINDRO["modelo"]), "T")


def test_conversiones_de_entrada_en_la_ficha():
    kv = _con(VALVULA, "modelo.caudal", {"Cv": 1.0, "p1_bar": 6, "p2_bar": 5, "b": 0.3})
    c = parse_ficha_neumatica(kv, "V").caudal
    assert c.C == pytest.approx(3.987, rel=1e-3) and any("VDI/VDE 2173" in h for h in c.hipotesis)
    s = parse_ficha_neumatica(_con(VALVULA, "modelo.caudal", {"S_mm2": 10, "b": 0.3, "m": 0.6}), "V").caudal
    assert s.C == pytest.approx(1.9919, rel=1e-3) and s.m == 0.6 and s.hipotesis == ()


def _yaml(tmp_path, ficha: dict, familia: bool = False):
    item = {"ref": "CIL-X", "name": "Cilindro X", "builder": "box",
            "params": {"width": 45, "depth": 45, "height": 94}, "weight": 0.5, "neumatico": ficha}
    doc = {"category": "x", "components": [item]}
    if familia:
        doc = {"category": "x", "families": [{
            "name_tpl": "Cilindro {ref}", "builder": "box", "param_keys": ["width", "depth", "height"],
            "weight": 0.5, "neumatico": ficha,
            "variants": [{"ref": "CIL-F32", "width": 45, "depth": 45, "height": 94},
                         {"ref": "CIL-F40", "width": 54, "depth": 54, "height": 105,
                          "neumatico": {"modelo": {"D_mm": 40, "d_mm": 16}}}]}]}
    (tmp_path / "a.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return str(tmp_path)


def test_el_loader_rechaza_un_bloque_neumatico_incompleto(tmp_path):
    with pytest.raises(ValueError, match=r"Componente 'CIL-X': neumatico\.modelo\.V_muerto_A_cm3: falta"):
        load_catalog(_yaml(tmp_path, _con(CILINDRO, "modelo.V_muerto_A_cm3", None)))


def test_el_loader_carga_la_ficha_y_la_familia_la_fusiona(tmp_path):
    cat = load_catalog(_yaml(tmp_path, CILINDRO))
    assert cat["CIL-X"].neumatico.modelo["D_mm"] == 32 and cat["CIL-X"].electrico is None
    cat = load_catalog(_yaml(tmp_path, CILINDRO, familia=True))
    assert cat["CIL-F32"].neumatico.modelo["D_mm"] == 32
    assert cat["CIL-F40"].neumatico.modelo["D_mm"] == 40 and cat["CIL-F40"].neumatico.modelo["d_mm"] == 16
    assert "neumatico" not in cat["CIL-F40"].specs  # el bloque no pasa a las specs
