"""Datos de ficha eléctrica (plan datos-de-corte-y-acometida, F1a: D1–D5, D12): el bloque
`electrico.datos` con su `fuente` y `a_confirmar`, validado y COMPLETO al cargar, fuera de
`modelo` (la firma del documento no se mueve), `T_max_C` en las 53 refs de tablero y la lectura
por tensión (`a_tension`)."""

from __future__ import annotations

import dataclasses
import re

import pytest
import yaml

from apolo.library.catalog import CATALOG, catalog_payload
from apolo.library.electrico import ficha_datos as FD
from apolo.library.electrico.ficha import ficha_payload
from apolo.library.loader import load_catalog

#: Una ref de prueba: un ITM 3P en riel (pide Icu, Ics y T_max_C).
ITM = {
    "funcion": "F", "simbolo": "itm_3p", "montaje": "din",
    "bornes": [{"id": "1", "rol": "potencia", "lado": "linea"}, {"id": "2", "rol": "potencia", "lado": "carga"}],
    "caminos": [{"de": "1", "a": "2", "tipo": "proteccion"}],
    "modelo": {"tipo": "itm", "In_A": 10, "curva": "C", "Icn_kA": 6, "polos": 3},
    "datos": {"Icu_kA": {240: 20, 415: 10}, "Ics_kA": {240: 15, 415: 7.5}, "T_max_C": 70},
    "fuente": "ficha de prueba",
}
SECC = {
    "funcion": "Q", "simbolo": "seccionador_3p", "montaje": "puerta",
    "bornes": [{"id": "1", "rol": "potencia"}, {"id": "2", "rol": "potencia"}],
    "caminos": [{"de": "1", "a": "2", "tipo": "NA", "accion": "mano"}],
    "modelo": {"tipo": "seccionador", "Ith_A": 25, "polos": 3},
    "datos": {"Icw_kA": 0.384, "Icw_t_s": 1, "Iq_kA": 10, "Iq_con": "fusible gG 35 A, 400 V", "T_max_C": 50},
    "fuente": "ficha de prueba",
}


def _cargar(tmp_path, electrico: dict, ref: str = "R"):
    comp = {"ref": ref, "name": "Prueba", "builder": "box", "weight": 1,
            "params": {"width": 54, "depth": 75, "height": 90}, "electrico": electrico}
    (tmp_path / "a.yaml").write_text(yaml.safe_dump({"category": "x", "components": [comp]}, allow_unicode=True),
                                     encoding="utf-8")
    return load_catalog(str(tmp_path))[ref].electrico


def _con(base: dict, **cambios) -> dict:
    out = {**base, **cambios}
    return {k: v for k, v in out.items() if v is not None}


def _datos(base: dict, **cambios) -> dict:
    d = {**base["datos"], **cambios}
    return {k: v for k, v in d.items() if v is not None}


# ── forma y validación ─────────────────────────────────────────────────────────────────────


def test_un_bloque_bueno_carga_con_sus_mapas_normalizados(tmp_path):
    f = _cargar(tmp_path, ITM)
    assert f.datos["Icu_kA"] == {240: 20.0, 415: 10.0} and f.datos["T_max_C"] == 70.0
    assert f.fuente == "ficha de prueba" and f.a_confirmar == ()
    assert "Icu_kA" not in f.modelo  # fuera de `modelo`: no lo emula la co-simulación (D1)
    s = _cargar(tmp_path, SECC)
    assert (s.datos["Icw_kA"], s.datos["Iq_con"]) == (0.384, "fusible gG 35 A, 400 V")


def test_lo_que_falta_va_en_a_confirmar_sin_valor(tmp_path):
    f = _cargar(tmp_path, _con(ITM, datos={"T_max_C": 70}, a_confirmar=["Icu_kA", "Ics_kA"]))
    assert f.a_confirmar == ("Icu_kA", "Ics_kA") and "Icu_kA" not in f.datos


MALOS = [
    (_con(ITM, datos=_datos(ITM, Icw_kA=1)), r"datos: clave «Icw_kA» que un «itm» no pide; válidas: Icu_kA, Ics_kA, T_max_C\. ¿Quisiste decir"),
    (_con(ITM, datos=_datos(ITM, T_max=70)), r"clave «T_max» .*¿Quisiste decir «T_max_C»"),
    (_con(ITM, datos=_datos(ITM, Ics_kA={240: 25, 415: 7.5})),
     r"datos\.Ics_kA: 25 kA a 240 V supera Icu_kA = 20 kA"),
    (_con(ITM, datos=_datos(ITM, Ics_kA={240: 15, 500: 5})), r"datos\.Ics_kA: a 500 V no hay Icu_kA"),
    (_con(ITM, datos=_datos(ITM, Icu_kA=20)), r"datos\.Icu_kA: se espera un mapa \{U_V: valor\}"),
    (_con(ITM, datos=_datos(ITM, Icu_kA={"alta": 20})), r"datos\.Icu_kA: la tensión «alta» no es un número"),
    (_con(ITM, datos=_datos(ITM, Icu_kA={240: 0, 415: 10})), r"datos\.Icu_kA\.240: se espera un número > 0"),
    (_con(ITM, datos=_datos(ITM, T_max_C="setenta")), r"datos\.T_max_C: se espera un número > 0"),
    (_con(SECC, datos=_datos(SECC, Iq_con=None)), r"datos\.Iq_con: con `Iq_kA` va la protección"),
    (_con(ITM, fuente=None), r"electrico\.fuente: falta"),
    (_con(ITM, fuente="  "), r"electrico\.fuente: falta"),
    (_con(ITM, datos=_datos(ITM, Icu_kA=None, Ics_kA=None)), r"datos\.Icu_kA: falta \(poder de corte último"),
    (_con(ITM, datos=_datos(ITM, T_max_C=None)), r"datos\.T_max_C: falta \(temperatura máxima"),
    (_con(SECC, datos=_datos(SECC, Icw_t_s=None)), r"datos\.Icw_t_s: falta"),
    (_con(ITM, a_confirmar=["Icu"]), r"a_confirmar: «Icu» no es un dato de esta ficha.*¿Quisiste decir «Icu_kA»"),
    (_con(ITM, a_confirmar=["esquema"]), r"«esquema» no es un dato de esta ficha"),  # sólo en una red
    (_con(ITM, a_confirmar=["T_max_C", "T_max_C"]), r"clave repetida"),
    (_con(ITM, a_confirmar="T_max_C"), r"a_confirmar: se espera una lista de claves"),
    (_con(ITM, datos=[70]), r"electrico\.datos: se espera un mapa"),
]


@pytest.mark.parametrize("bloque,mensaje", MALOS)
def test_un_bloque_de_datos_mal_escrito_o_incompleto_no_carga(tmp_path, bloque, mensaje):
    with pytest.raises(ValueError, match=r"Componente 'R': electrico") as exc:
        _cargar(tmp_path, bloque)
    assert re.search(mensaje, str(exc.value)), str(exc.value)


def test_completitud_por_tipo_y_por_montaje(tmp_path):
    """El tipo pide sus datos en cualquier montaje; `T_max_C` sólo dentro del tablero."""
    assert FD.requeridos("itm", "din") == ("Icu_kA", "Ics_kA", "T_max_C")
    assert FD.requeridos("itm", "campo") == ("Icu_kA", "Ics_kA")
    assert FD.requeridos("contactor", "din") == ("T_max_C",)
    assert FD.requeridos("motor", "campo") == ()
    assert FD.requeridos(None, "placa") == ("T_max_C",)
    sin_tmax = _con(ITM, montaje="campo", datos=_datos(ITM, T_max_C=None))
    assert "T_max_C" not in _cargar(tmp_path, sin_tmax).datos
    with pytest.raises(ValueError, match=r"datos\.Icu_kA: falta"):
        _cargar(tmp_path, _con(sin_tmax, datos={"Ics_kA": {240: 1}}))


def test_un_bloque_sin_datos_en_campo_carga_igual_que_antes(tmp_path):
    motor = {"funcion": "M", "simbolo": "motor_3f", "montaje": "campo",
             "bornes": [{"id": i, "rol": "potencia"} for i in ("U1", "V1", "W1")]}
    f = _cargar(tmp_path, motor)
    assert (f.datos, f.fuente, f.a_confirmar) == ({}, "", ())
    assert not {"datos", "fuente", "a_confirmar"} & set(ficha_payload(f))


def test_la_red_nombra_su_esquema_sin_valor_y_su_icc_supuesta(tmp_path):
    red = {"funcion": "G", "simbolo": "red_3f", "montaje": "campo",
           "bornes": [{"id": "L1", "rol": "potencia"}, {"id": "L2", "rol": "potencia"},
                      {"id": "L3", "rol": "potencia"}, {"id": "PE", "rol": "tierra"}],
           "fuentes": [{"polos": {"L1": "L1", "L2": "L2", "L3": "L3", "PE": "PE"}, "tension": "220 VAC 3F 60 Hz"}],
           "modelo": {"tipo": "red", "sistema": "3F", "U_V": 220, "Icc_kA": 10, "X_R": 1.5},
           "a_confirmar": ["Icc_kA", "X_R", "esquema"], "fuente": "criterio de diseño: prueba"}
    f = _cargar(tmp_path, red)
    assert f.a_confirmar == ("Icc_kA", "X_R", "esquema") and "esquema" not in f.modelo
    with pytest.raises(ValueError, match=r"«RA_ohm» no es un dato"):
        _cargar(tmp_path, {**red, "a_confirmar": ["RA_ohm"]})


def test_la_familia_fusiona_los_datos_clave_a_clave(tmp_path):
    familia = {
        "family": "F", "name_tpl": "ITM {ref}", "builder": "box",
        "param_keys": ["width", "depth", "height"], "weight": 1,
        "electrico": {**ITM, "datos": {"T_max_C": 70}, "a_confirmar": ["Icu_kA", "Ics_kA"]},
        "variants": [{"ref": "F1", "width": 54, "depth": 75, "height": 90,
                      "electrico": {"datos": {"Icu_kA": {240: 20}, "Ics_kA": {240: 15}}, "a_confirmar": []}},
                     {"ref": "F2", "width": 54, "depth": 75, "height": 90}],
    }
    (tmp_path / "a.yaml").write_text(yaml.safe_dump({"category": "x", "families": [familia]}), encoding="utf-8")
    cat = load_catalog(str(tmp_path))
    assert cat["F1"].electrico.datos == {"T_max_C": 70.0, "Icu_kA": {240: 20.0}, "Ics_kA": {240: 15.0}}
    assert cat["F2"].electrico.datos == {"T_max_C": 70.0} and cat["F2"].electrico.a_confirmar == ("Icu_kA", "Ics_kA")


# ── a_tension (D2) ─────────────────────────────────────────────────────────────────────────


def test_a_tension_toma_la_menor_tension_tabulada_que_alcanza():
    icu = {240: 20.0, 415: 10.0}
    assert FD.a_tension(icu, 220) == 20.0   # la red de 220 V lee la fila de 220…240 V
    assert FD.a_tension(icu, 240) == 20.0
    assert FD.a_tension(icu, 380) == 10.0   # la de 380 V, la de 380…415 V
    assert FD.a_tension(icu, 415) == 10.0
    assert FD.a_tension(icu, 440) is None   # arriba: sin dato, nunca una extrapolación
    assert FD.a_tension({}, 220) is None and FD.a_tension(None, 220) is None
    assert FD.a_tension({"240": 20}, 100) == 20.0  # las claves del JSON del catálogo también


# ── el catálogo ────────────────────────────────────────────────────────────────────────────


def _tablero():
    return {r: c.electrico for r, c in CATALOG.items()
            if c.electrico is not None and c.electrico.montaje in FD.TABLERO}


def test_las_61_refs_de_tablero_dicen_su_t_max_o_la_dejan_a_confirmar():
    tab = _tablero()
    assert len(tab) == 61  # 53 de la F1a + los 8 diferenciales de la F1b (T_max_C a confirmar)
    sin = [r for r, f in tab.items() if "T_max_C" not in f.datos and "T_max_C" not in f.a_confirmar]
    assert not sin, sin
    con = {r for r, f in tab.items() if "T_max_C" in f.datos}
    assert len(con) == 34  # el resto (19 + 8) a confirmar: sin ficha verificada (bitácoras F1a, F1b)
    assert all(40 <= tab[r].datos["T_max_C"] <= 70 for r in con)


def test_cada_cifra_del_catalogo_trae_su_fuente_y_es_honesta():
    for r, c in CATALOG.items():
        f = c.electrico
        if f is None or not (f.datos or f.a_confirmar):
            continue
        assert f.fuente, r
        for k in FD.requeridos(f.modelo.get("tipo"), f.montaje):
            assert k in f.datos or k in f.a_confirmar, (r, k)


def test_poder_de_corte_de_las_refs_verificadas():
    """Las cifras que entraron con su ficha (bitácora F1a); las demás protecciones, a confirmar."""
    d = {r: CATALOG[r].electrico.datos for r in CATALOG if CATALOG[r].electrico is not None}
    assert d["ITM-C10-3P"]["Icu_kA"] == {240: 20.0, 415: 10.0} == d["ITM-C6-2P"]["Icu_kA"]
    assert d["ITM-C2-2P"]["Ics_kA"] == {240: 50.0, 415: 50.0}
    for gm in ("GM-1-1.6A", "GM-1.6-2.5A", "GM-2.5-4A", "GM-4-6.3A", "GM-6-10A"):
        assert d[gm]["Icu_kA"] == d[gm]["Ics_kA"] == {240: 100.0, 415: 100.0}
    assert (d["SECC-25A-3P"]["Icw_kA"], d["SECC-40A-3P"]["Icw_kA"]) == (0.384, 0.48)
    for itm in ("ITM-C6-3P", "ITM-C16-3P", "ITM-C20-3P", "ITM-C2-1PN", "ITM-C6-1PN"):
        assert set(CATALOG[itm].electrico.a_confirmar) == {"Icu_kA", "Ics_kA"}, itm
    assert {"cartucho_U_V", "cartucho_Icn_A", "cartucho_Icn_x_In"} <= set(CATALOG["BORNE-FUS-5X20"].electrico.a_confirmar)
    for red in ("RED-3F-220V-60HZ", "RED-2F-220V-60HZ"):  # sin esquema de tierra: a confirmar
        f = CATALOG[red].electrico
        assert "esquema" not in f.modelo and "esquema" in f.a_confirmar


def test_el_payload_del_catalogo_publica_datos_fuente_y_a_confirmar():
    p = ficha_payload(CATALOG["ITM-C10-3P"].electrico)
    assert p["datos"]["Icu_kA"] == {"240": 20.0, "415": 10.0} and p["fuente"].startswith("Schneider")
    assert "a_confirmar" not in p
    q = ficha_payload(CATALOG["ITM-C6-3P"].electrico)
    assert q["a_confirmar"] == ["Icu_kA", "Ics_kA"] and q["datos"] == {"T_max_C": 70.0}
    import json

    json.dumps(catalog_payload())  # las claves de tensión salen como texto: JSON válido


# ── la firma del documento no se mueve (D1, D11) ───────────────────────────────────────────


def test_los_datos_de_ficha_no_entran_a_la_firma_del_documento(monkeypatch):
    """Con los mismos comandos, quitar `datos`/`fuente`/`a_confirmar` de todas las fichas da la
    MISMA firma: los datos no llegan a `Dispositivo` (el banco antes/después, en la bitácora)."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from tablero_electrico import arranque_directo

    from apolo.doc.document import Document
    from apolo.services.escenarios import firma_documento

    def firma() -> str:
        d = Document("firma")
        d.execute_many(arranque_directo())
        return firma_documento(d)

    con_datos = firma()
    for ref, comp in list(CATALOG.items()):
        f = comp.electrico
        if f is not None and (f.datos or f.fuente or f.a_confirmar):
            sin = dataclasses.replace(f, datos={}, fuente="", a_confirmar=())
            monkeypatch.setitem(CATALOG, ref, dataclasses.replace(comp, electrico=sin))
    assert firma() == con_datos


def test_ficha_datos_esta_en_el_contrato_de_extensiones():
    from apolo import extensiones, extensiones_api

    assert set(extensiones_api.MODULOS["apolo.library.electrico.ficha_datos"]) == {
        "REQUERIDOS", "a_tension", "requeridos"}
    assert extensiones.CONTRATO_EXTENSIONES == 1  # agregar no sube el contrato (D12)
