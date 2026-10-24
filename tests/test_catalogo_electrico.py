"""Catálogo eléctrico (plan V8.1 F2, D5/D6): el bloque `electrico:` del YAML, validado al
cargar, las ~60 refs nuevas de la faja piloto y los bloques agregados a refs que ya existían
(sin tocar su geometría ni sus claves)."""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest
import yaml

from apolo.assembly.grouping import CAT2SUB, SUB2ROLE
from apolo.library.catalog import CATALOG, CATEGORIES, build_component, refs_in_category
from apolo.library.checks import FEA_HARDWARE_CATS, HARDWARE_CATS
from apolo.library.electrico.ficha import FUNCIONES, MONTAJES
from apolo.library.electrico.modelo import dispositivo_desde_ficha
from apolo.library.loader import load_catalog

RAIZ = Path(__file__).resolve().parents[1]
NUEVAS_CATEGORIAS = ["alimentacion_electrica", "proteccion_electrica", "maniobra_control",
                     "conexion_electrica"]
NUEVAS = {
    "alimentacion_electrica": ["RED-3F-220V-60HZ", "RED-3F-380-220V-60HZ", "FUENTE-24VDC-2.5A",
                               "FUENTE-24VDC-5A", "RED-2F-220V-60HZ", "RED-1F-220V-60HZ"],
    "proteccion_electrica": ["SECC-25A-3P", "SECC-40A-3P", "ITM-C6-3P", "ITM-C10-3P", "ITM-C16-3P",
                             "ITM-C20-3P", "ITM-C2-2P", "ITM-C6-2P", "ITM-C2-1PN", "ITM-C6-1PN",
                             "GM-1-1.6A", "GM-1.6-2.5A", "GM-2.5-4A", "GM-4-6.3A", "GM-6-10A",
                             "GM-AUX-1NA1NC", "RT-2.5-4A", "RT-4-6A"],
    "maniobra_control": ["CONT-9A-24VDC", "CONT-9A-220VAC", "CONT-12A-24VDC", "CONT-12A-220VAC",
                         "CONT-18A-24VDC", "CONT-18A-220VAC", "CONT-AUX-1NA1NC", "RELE-INT-24VDC",
                         "RELE-INT-230V", "PLC-14DI-10DO-24VDC"],
    "mandos": ["PULS-22-VERDE-NA", "PULS-22-ROJO-NC", "PULS-22-AZUL-NA", "SEL-22-2POS-1NA",
               "SEL-22-3POS-2NA", "PILOTO-24V-VERDE", "PILOTO-24V-ROJO", "PILOTO-24V-AMBAR"],
    "sensores": ["SENS-IND-M18-PNP"],
    "conexion_electrica": ["BORNE-PASO-2.5", "BORNE-PASO-4", "BORNE-PE-2.5", "BORNE-PE-4",
                           "BORNE-FUS-5X20", "COND-H05VK-0.75", "COND-H05VK-1", "COND-H07VK-1.5",
                           "COND-H07VK-2.5", "COND-H07VK-4", "CABLE-4G1.5", "CABLE-4G2.5",
                           "CABLE-4G4", "CABLE-5G1", "CABLE-7G1", "CABLE-3X0.75"],
    "tableros": ["GAB-6040", "GAB-8060"],
}
TODAS_NUEVAS = [r for refs in NUEVAS.values() for r in refs]
# la seta en caja de superficie (plan seta-de-emergencia D4): misma ficha que ESTOP-40
#: los mandos de seguridad de dos canales (plan mandos-de-seguridad D1–D3), eléctricos
SEGURIDAD = ["ESTOP-40-2NC", "ESTOP-40-CAJA-2NC", "RESG-2NC", "RS-2C-24VDC"]
SETAS = ["ESTOP-40-CAJA"] + SEGURIDAD
EXISTENTES = ["VFD-1K5-220", "VFD-2K2-220", "ESTOP-40", "BOTONERA-2", "FOTO-M18", "TABLERO-5040",
              "MOTOR-037", "MOTOR-075", "MOTOR-150", "MOTOR-150-EH"] + refs_in_category("motorreductores_sinfin")
MARCAS = ("SCHNEIDER", "SIEMENS", "ABB", "PHOENIX", "WEIDMULLER", "OMRON", "SICK", "LAPP",
          "MEANWELL", "MEAN-WELL", "RITTAL", "FINDER", "DELTA", "TESYS", "SIRIUS")


# ── las refs nuevas ───────────────────────────────────────────────────────────────────────


def test_las_61_refs_nuevas_cargan_en_su_categoria():
    # 59 de V8.1 + las redes 2F y 1F+N de V8.3 F2 (D15)
    assert len(TODAS_NUEVAS) == 61 == len(set(TODAS_NUEVAS))
    for categoria, refs in NUEVAS.items():
        for ref in refs:
            assert CATALOG[ref].category == categoria, ref
    for categoria in NUEVAS_CATEGORIAS:
        extra = ["RS-2C-24VDC"] if categoria == "maniobra_control" else []  # mandos-de-seguridad D3
        assert sorted(refs_in_category(categoria)) == sorted(NUEVAS[categoria] + extra)
    # + ESTOP-40-CAJA (seta D4) + 8 de union-en-perfil-hueco + 3 UCT + TAMBOR-102-RET (faja v4)
    # + 4 pernos de cuello cuadrado DIN 603 (F6) + 10 del armado del tablero (V8.5 F1a)
    # + 5 de mandos-de-seguridad (las 4 de SEGURIDAD y RESG-LENGUETA)
    assert len(CATALOG) == 420  # + 27 del catálogo neumático (V8.9 F1a)


@pytest.mark.parametrize("ref", TODAS_NUEVAS + SETAS)
def test_cada_ref_nueva_es_honesta(ref):
    c = CATALOG[ref]
    s = c.specs
    assert s["linea_referencia"].strip(), ref
    assert s["cotas_verificadas"] is False, ref
    assert "verificar con" in c.description.lower(), ref
    assert ("cost" in s) or ("cost_por_m" in s), f"{ref}: sin precio referencial"
    assert not any(m in ref.replace(" ", "").upper() for m in MARCAS), f"{ref}: marca en la ref"
    assert c.electrico is not None, ref
    if "modulos_DIN" in s:  # aparato modular: ancho = n × 18 mm (DIN 43880)
        shape, _ = build_component(ref)
        bb = shape.bounding_box()
        assert math.isclose(bb.size.X, 18 * s["modulos_DIN"], abs_tol=0.01), ref


def test_conductores_y_cables_por_metro_con_equivalente_local():
    for ref in NUEVAS["conexion_electrica"]:
        c = CATALOG[ref]
        if not ref.startswith(("COND-", "CABLE-")):
            continue
        assert c.cuttable and c.default_length == 1000 and c.specs["cost_por_m"] > 0, ref
        assert "Perú" in c.description or "local" in c.description, ref
        assert c.electrico.conductor.seccion_mm2 == c.specs["seccion_mm2"], ref
    hilos = CATALOG["CABLE-4G1.5"].electrico.conductor.hilos
    assert [(h.id, h.color) for h in hilos] == [("1", "BK"), ("2", "BK"), ("3", "BK"), ("PE", "GNYE")]
    # H07V-K empieza en 1,5 mm²: las secciones menores son H05V-K (300/500 V)
    assert CATALOG["COND-H05VK-0.75"].electrico.conductor.tension_aislamiento == "300/500 V"
    assert CATALOG["COND-H07VK-1.5"].electrico.conductor.tension_aislamiento == "450/750 V"


def test_guardamotores_cubren_1_a_10_a_sin_huecos():
    gms = sorted((CATALOG[r].specs["Ir_min_A"], CATALOG[r].specs["Ir_max_A"]) for r in NUEVAS["proteccion_electrica"]
                 if r.startswith("GM-") and "AUX" not in r)
    assert len(gms) == 5 and gms[0][0] == 1.0 and gms[-1][1] == 10.0
    assert all(b[0] <= a[1] for a, b in zip(gms, gms[1:]))  # cada rango empieza dentro del anterior
    for r in NUEVAS["proteccion_electrica"]:
        f = CATALOG[r].electrico
        assert f.protege_motor == (r.startswith(("GM-", "RT-")) and "AUX" not in r), r


def test_red_de_lima_sin_neutro_y_su_icc_declarada():
    red = CATALOG["RED-3F-220V-60HZ"]
    [fuente] = red.electrico.fuentes
    assert fuente.tension.fases == 3 and not fuente.tension.neutro and fuente.tension.linea == 220
    assert {p for _, p in fuente.polos} == {"L1", "L2", "L3", "PE"}
    assert red.specs["icc_kA"] == 10 and red.specs["icc_supuesta"] is True
    assert "SUPUESTA" in red.description
    con_n = CATALOG["RED-3F-380-220V-60HZ"].electrico.fuentes[0].tension
    assert con_n.neutro and con_n.linea == 380 and con_n.fase == 220


def test_plc_tiene_las_es_del_contrato():
    f = CATALOG["PLC-14DI-10DO-24VDC"].electrico
    ids = set(f.ids_bornes)
    entradas = {f"I0.{i}" for i in range(8)} | {f"I1.{i}" for i in range(6)}
    salidas = {f"Q0.{i}" for i in range(8)} | {"Q1.0", "Q1.1"}
    assert entradas | salidas | {"L+", "M", "AI0", "AI1", "PE"} <= ids
    assert {c.a for c in f.caminos} == salidas and all(c.de == "3L+" for c in f.caminos)
    assert sum(1 for c in f.cargas if c.tipo == "entrada" and c.bornes[1] == "1M") == 14


def test_contactores_con_bobina_de_24vdc_y_220vac():
    for amp in (9, 12, 18):
        dc, ac = CATALOG[f"CONT-{amp}A-24VDC"].electrico, CATALOG[f"CONT-{amp}A-220VAC"].electrico
        assert dc.cargas[0].tension.tipo == "DC" and dc.cargas[0].tension.linea == 24
        assert ac.cargas[0].tension.tipo == "AC" and ac.cargas[0].tension.linea == 220
        assert dc.modelo["Ie_AC3_A"] == ac.modelo["Ie_AC3_A"] == amp


# ── categorías: UI, subsistema, FEA ───────────────────────────────────────────────────────


def test_categorias_nuevas_al_final_y_en_su_subsistema():
    i = CATEGORIES.index(NUEVAS_CATEGORIAS[0])  # al final, antes de las neumáticas (V8.9)
    assert CATEGORIES[i:i + 4] == NUEVAS_CATEGORIAS and CATEGORIES[i + 4:] == [
        "cilindros_neumaticos", "valvulas_neumaticas", "aire_comprimido"]
    tree = (RAIZ / "ui" / "src" / "panels" / "Tree.tsx").read_text(encoding="utf-8")
    for cat in NUEVAS_CATEGORIAS:
        assert CAT2SUB[cat] == "Sensores y control"
        assert re.search(rf'\b{cat}:\s*"Sensores y control"', tree), f"Tree.tsx: CAT2SUB sin {cat}"
        assert cat in FEA_HARDWARE_CATS and cat not in HARDWARE_CATS
    assert SUB2ROLE["Sensores y control"] == "electrico"
    assert HARDWARE_CATS == {"tornilleria", "rodamientos", "pernos"}


# ── refs que ya existían: bloque nuevo, nada más ──────────────────────────────────────────


def test_refs_fijadas_conservan_specs_y_geometria():
    assert CATALOG["VFD-1K5-220"].specs == {
        "potencia_kW": 1.5, "potencia_HP": 2, "tension": "220V 3F", "corriente_A": 8.5,
        "control": "vectorial sensorless", "proteccion": "STO", "cost": 240}  # cost: V8.1 F4
    assert CATALOG["VFD-2K2-220"].specs == {
        "potencia_kW": 2.2, "potencia_HP": 3, "tension": "220V 3F", "corriente_A": 11.0,
        "control": "vectorial sensorless", "proteccion": "STO", "cost": 280}
    # la seta ganó cotas y geometría propias (seta-de-emergencia D4/D6) y conserva las de siempre
    estop = CATALOG["ESTOP-40"].specs
    assert {k: estop[k] for k in ("tipo", "contacto", "norma")} == {
        "tipo": "hongo Ø40", "contacto": "NC apertura positiva", "norma": "ISO 13850"}
    assert estop["cotas_verificadas"] is False and estop["linea_referencia"].strip()
    foto = CATALOG["FOTO-M18"].specs  # + linea_referencia y cost referencial (V8.1 F4)
    assert {k: foto[k] for k in ("rosca", "alcance_mm", "salida", "tension")} == {
        "rosca": "M18", "alcance_mm": 400, "salida": "PNP", "tension": "10-30 VDC"}
    assert foto["cost"] == 28 and foto["cotas_verificadas"] is False
    assert CATALOG["MOTOR-150-EH"].specs["tension"] == "220/380V" and CATALOG["MOTOR-150-EH"].weight == 25.0
    nmrv = CATALOG["NMRV-090"]
    assert "electrico" not in nmrv.specs and nmrv.specs["potencia_kW"] == 2.2 and nmrv.weight == 45.0
    # ESTOP-40 dejó la caja de 72×72×70: leyenda Ø60 y 33 mm delante + 44 detrás de la puerta (D6)
    for ref, (dx, dy, dz) in {"VFD-2K2-220": (140, 145, 160), "ESTOP-40": (60, 60, 77),
                              "BOTONERA-2": (80, 60, 120), "TABLERO-5040": (500, 200, 400)}.items():
        bb = build_component(ref)[0].bounding_box()
        assert (round(bb.size.X), round(bb.size.Y), round(bb.size.Z)) == (dx, dy, dz), ref


def test_refs_existentes_ganan_su_bloque():
    for ref in EXISTENTES:
        assert CATALOG[ref].electrico is not None, ref
    for ref in ("VFD-1K5-220", "VFD-2K2-220"):
        f = CATALOG[ref].electrico
        assert f.protege_motor and f.funcion == "T"
        assert {"L1", "L2", "L3", "U", "V", "W", "PE", "DI1", "DI2", "DI3", "DI4", "COM", "AI1",
                "+10V", "GND", "RA", "RB", "RC", "S1", "S2", "SCM"} == set(f.ids_bornes)
        assert len(f.fuentes) == 2  # salida al motor y +10 V del potenciómetro
    assert CATALOG["ESTOP-40"].electrico.parada_emergencia
    assert [c.tipo for c in CATALOG["ESTOP-40"].electrico.caminos] == ["NC"]
    assert {c.grupo for c in CATALOG["BOTONERA-2"].electrico.caminos} == {"marcha", "paro"}
    assert CATALOG["FOTO-M18"].electrico.caminos[0].accion == "señal"


@pytest.mark.parametrize("ref", ["MOTOR-037", "MOTOR-075", "MOTOR-150", "MOTOR-150-EH"]
                         + refs_in_category("motorreductores_sinfin"))
def test_placa_del_motor(ref):
    f = CATALOG[ref].electrico
    [carga] = f.cargas
    assert carga.tipo == "motor" and carga.bornes == ("U1", "V1", "W1") and f.funcion == "M"
    m = f.modelo
    for k in ("P_kW", "U_V", "conexion", "In_A", "cos_phi", "eta", "Ia_In", "Ta_Tn", "Tk_Tn", "polos", "f_Hz"):
        assert k in m, f"{ref}: falta {k} en la placa"
    assert m["P_kW"] == CATALOG[ref].specs["potencia_kW"]
    # In = P / (√3 · U · η · cosφ), la fórmula DECLARADA en el YAML
    calc = m["P_kW"] * 1000 / (math.sqrt(3) * m["U_V"] * m["eta"] * m["cos_phi"])
    assert m["In_A"] == pytest.approx(calc, rel=0.01), ref
    assert m["U_V"] in [round(v) for v in carga.tension.valores] or carga.tension.linea == m["U_V"]


def test_toda_ficha_nombra_sus_propios_bornes():
    fichas = {ref: c.electrico for ref, c in CATALOG.items() if c.electrico is not None}
    assert len(fichas) == len(TODAS_NUEVAS) + len(EXISTENTES) + len(SETAS)
    for ref, f in fichas.items():
        ids = f.ids_bornes
        assert len(ids) == len(set(ids)), ref
        assert f.funcion in FUNCIONES and f.montaje in MONTAJES, ref
        for c in f.caminos:
            assert c.de in ids and c.a in ids, ref
        for carga in f.cargas:
            assert set(carga.bornes) <= set(ids), ref
        for fuente in f.fuentes:
            assert {b for b, _ in fuente.polos} <= set(ids), ref
        assert ids or f.conductor is not None, ref
    assert CATALOG["PERFIL-4040"].electrico is None and CATALOG["6205"].electrico is None


def test_bornera_se_expande_por_cantidad():
    paso = dispositivo_desde_ficha("-X1", "BORNE-PASO-2.5", CATALOG["BORNE-PASO-2.5"].electrico, cantidad=3)
    assert paso.ids_bornes == ("1", "2", "3") and paso.bornera
    fus = dispositivo_desde_ficha("-F9", "BORNE-FUS-5X20", CATALOG["BORNE-FUS-5X20"].electrico, cantidad=2)
    assert fus.ids_bornes == ("1.1", "1.2", "2.1", "2.2")
    assert [(c.de, c.a, c.tipo) for c in fus.caminos] == [("1.1", "1.2", "proteccion"), ("2.1", "2.2", "proteccion")]
    with pytest.raises(ValueError, match="sólo vale en una bornera"):
        dispositivo_desde_ficha("-Q1", "CONT-9A-24VDC", CATALOG["CONT-9A-24VDC"].electrico, cantidad=2)


# ── el loader valida el bloque ────────────────────────────────────────────────────────────


BUENO = {
    "funcion": "Q", "simbolo": "contactor_3p", "montaje": "din", "perdidas_W": 2,
    "bornes": [{"id": "1", "rol": "potencia", "lado": "linea"}, {"id": "2", "rol": "potencia", "lado": "carga"},
               {"id": "A1", "rol": "bobina"}, {"id": "A2", "rol": "bobina"}],
    "caminos": [{"de": "1", "a": "2", "tipo": "NA", "accion": "bobina"}],
    "cargas": [{"bornes": ["A1", "A2"], "tension": "24 VDC", "tipo": "bobina"}],
    "modelo": {"Ie_AC3_A": 9},
}


def _cargar(tmp_path, electrico=None, *, familia: dict | None = None):
    comp = {"ref": "R", "name": "Prueba", "builder": "box", "weight": 1,
            "params": {"width": 18, "depth": 70, "height": 90}}
    if electrico is not None:
        comp["electrico"] = electrico
    doc = {"category": "x", "components": [comp]} if familia is None else {"category": "x", "families": [familia]}
    (tmp_path / "a.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return load_catalog(str(tmp_path))


def test_un_bloque_bueno_carga(tmp_path):
    f = _cargar(tmp_path, BUENO)["R"].electrico
    assert f.funcion == "Q" and f.ids_bornes == ("1", "2", "A1", "A2")
    assert f.caminos[0].accion == "bobina" and f.cargas[0].tension.linea == 24
    assert f.modelo == {"Ie_AC3_A": 9} and f.perdidas_W == 2.0
    assert _cargar(tmp_path)["R"].electrico is None  # sin bloque: pieza mecánica


def test_familia_fusiona_el_modelo_de_cada_variante(tmp_path):
    familia = {
        "family": "F", "name_tpl": "Motor {ref}", "builder": "box",
        "param_keys": ["width", "depth", "height"], "weight": 1,
        "electrico": {"funcion": "M", "simbolo": "motor_3f", "montaje": "campo",
                      "bornes": [{"id": i, "rol": "potencia"} for i in ("U1", "V1", "W1")],
                      "cargas": [{"bornes": ["U1", "V1", "W1"], "tension": "220/380 VAC 3F", "tipo": "motor"}],
                      "modelo": {"polos": 4}},
        "variants": [{"ref": "F1", "width": 10, "depth": 5, "height": 5, "electrico": {"modelo": {"In_A": 1.2}}},
                     {"ref": "F2", "width": 20, "depth": 5, "height": 5}],
    }
    cat = _cargar(tmp_path, familia=familia)
    assert cat["F1"].electrico.modelo == {"polos": 4, "In_A": 1.2}
    assert cat["F2"].electrico.modelo == {"polos": 4}
    assert "electrico" not in cat["F1"].specs  # el bloque de la variante no ensucia sus specs


def _con(**cambios) -> dict:
    out = {k: v for k, v in BUENO.items()}
    out.update(cambios)
    return out


MALOS = [
    (_con(bornes=BUENO["bornes"] + [{"id": "A1", "rol": "bobina"}]), r"bornes\[4\].*«A1» repetido"),
    (_con(caminos=[{"de": "1", "a": "3", "tipo": "NA", "accion": "bobina"}]), r"caminos\[0\]\.a: el borne «3» no existe"),
    (_con(cargas=[{"bornes": ["A1", "A3"], "tension": "24 VDC", "tipo": "bobina"}]),
     r"el borne «A3» no existe.*¿Quisiste decir «A1»"),
    (_con(cargas=[{"bornes": ["A1", "A2"], "tension": "24 voltios", "tipo": "bobina"}]), r"tensión ilegible «24 voltios»"),
    (_con(fuentes=[{"polos": {"1": "+", "2": "L1"}, "tension": "24 VDC"}]), r"fuentes\[0\]\.polos\.2: «L1» no es válido"),
    (_con(fuentes=[{"polos": {"1": "L1", "2": "L2"}, "tension": "220 VAC 3F"}]), r"mapear los polos L3"),
    (_con(tensión="24 VDC"), r"clave desconocida «tensión»"),
    (_con(simbolos="x"), r"clave desconocida «simbolos».*¿Quisiste decir «simbolo»"),
    (_con(funcion="Z"), r"electrico\.funcion: «Z» no es válido"),
    (_con(montaje="riel"), r"electrico\.montaje: «riel» no es válido"),
    (_con(caminos=[{"de": "1", "a": "2", "tipo": "NA"}]), r"un contacto NA necesita `accion`"),
    (_con(caminos=[{"de": "1", "a": "2", "tipo": "fijo", "accion": "mano"}]), r"un camino `fijo` no lleva `accion`"),
    (_con(cargas=[]), r"movidos por `bobina` pero ninguna carga de tipo bobina"),
    (_con(cargas=[{"bornes": ["A1", "A2"], "tension": "220 VAC 3F", "tipo": "motor"}]), r"trifásica.*va entre 3 bornes"),
    (_con(bornes=[{"id": "-K1:1", "rol": "potencia"}], caminos=[], cargas=[]), r"no puede llevar espacios ni «:»"),
    (_con(bornes=[{"id": "1", "rol": "fuerza"}], caminos=[], cargas=[]), r"bornes\[0\]\.rol: «fuerza» no es válido"),
    (_con(funcion=None), r"electrico\.funcion: falta"),
    (_con(bornes=[], caminos=[], cargas=[]), r"al menos un borne"),
    (_con(bornera=True), r"una bornera no tiene cargas ni fuentes"),
    (_con(perdidas_W=-1), r"perdidas_W: se espera un número ≥ 0"),
    (_con(protege_motor="si"), r"electrico\.protege_motor: se espera true o false"),
    (_con(cargas=[{"bornes": ["A1", "A2"], "tension": "24 VDC", "tipo": "bobina", "polar": "no"}]),
     r"cargas\[0\]\.polar: se espera true o false"),
    ({"funcion": "W", "simbolo": "cable", "montaje": "campo",
      "conductor": {"seccion_mm2": 0, "tension_aislamiento": "300/500 V"}}, r"conductor\.seccion_mm2: se espera un número > 0"),
    ({"funcion": "W", "simbolo": "cable", "montaje": "campo",
      "conductor": {"seccion_mm2": 1, "tension_aislamiento": "300/500 V", "hilos": [{"id": "1", "color": "NEGRO"}]}},
     r"hilos\[0\]\.color: «NEGRO» no es válido"),
]


@pytest.mark.parametrize("bloque,mensaje", MALOS)
def test_un_bloque_mal_escrito_no_carga(tmp_path, bloque, mensaje):
    with pytest.raises(ValueError, match=r"Componente 'R': electrico") as exc:
        _cargar(tmp_path, bloque)
    assert re.search(mensaje, str(exc.value)), str(exc.value)
