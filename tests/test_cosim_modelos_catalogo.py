"""El catálogo y los modelos de la co-simulación hablan el mismo idioma (plan V8.3 F2, D7, D10,
D15): cada ref activa trae un `modelo.tipo` que tiene modelo y todos sus parámetros; las pasivas
no lo traen; los nombres de señal son los de D10; el YAML se valida al cargar (`tipo`, `clase`
en una sola forma, `sistema` de la red) y la red 2F se lee."""

from __future__ import annotations

import re

import pytest
import yaml

from apolo.cosim.modelos import MODELOS, crear_modelo
from apolo.library.catalog import CATALOG
from apolo.library.electrico.ajustes import validar_ajustes
from apolo.library.electrico.ficha import TIPOS_MODELO
from apolo.library.electrico.tension import parse_tension, polos_validos, tension_entre
from apolo.library.loader import load_catalog
from apolo.services.cosim_aire import ficha_plana

#: Lo que un instalador fija sí o sí (un rango del catálogo): un valor cualquiera del rango.
_DATOS_DE_BANDA = ("cierre_ms", "apertura_ms", "AI_V")


def ajustes_minimos(modelo: dict) -> dict:
    return {k: (v[0] + v[1]) / 2 for k, v in modelo.items()
            if isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)
            and k not in _DATOS_DE_BANDA}


def fichas():
    return {ref: c.electrico for ref, c in CATALOG.items() if c.electrico is not None}


def test_los_tipos_del_yaml_son_los_modelos():
    assert set(TIPOS_MODELO) == set(MODELOS)


def _modelo_cosim(ref: str, f) -> dict:
    """El `modelo` que llega a la co-simulación: el eléctrico con la ficha de aire plana (V8.9 F3,
    `services/cosim_aire.py`), como en el snapshot."""
    n = CATALOG[ref].neumatico
    return {**f.modelo, "aire": ficha_plana(n)} if n is not None else f.modelo


def test_toda_ref_activa_se_emula_con_su_catalogo():
    pasivas = []
    for ref, f in fichas().items():
        modelo = _modelo_cosim(ref, f)
        # el presostato (V8.9 F8) tiene su ajuste en la ficha de AIRE: lo pone quien lo instala
        m = crear_modelo("-X1", ref, modelo, {**ajustes_minimos(f.modelo), **ajustes_minimos(modelo.get("aire", {}))})
        if m is None:
            pasivas.append(ref)
            continue
        assert m.tipo == f.modelo["tipo"], ref
        m.paso(0.002, {})
        for nombre in m.senales():
            assert re.fullmatch(r"-X1\.[%\w.]+", nombre), (ref, nombre)
    # sólo lo que no tiene comportamiento propio: bornes, conductores, gabinetes y los contactos
    # auxiliares (siguen a su aparato); las electroválvulas ya tienen el suyo (V8.9 F3)
    for ref in pasivas:
        f = fichas()[ref]
        assert f.funcion in ("X", "W", "U") or f.simbolo == "contactos_aux", ref


def test_toda_ref_de_aire_con_estado_se_emula():
    """V8.9 F3: cilindros, FRL y válvulas de corte arman su modelo de aire con la ficha del
    catálogo (más la carrera del cilindro y el ajuste del FRL, que pone quien lo instala)."""
    from apolo.cosim.neumatica import MODELOS_AIRE, crear_modelo_aire

    vistos = set()
    for ref, c in CATALOG.items():
        if c.neumatico is None or c.neumatico.tipo not in MODELOS_AIRE:
            continue
        aire = {**ficha_plana(c.neumatico), "carrera_mm": 100.0}
        m = crear_modelo_aire("-X1", ref, aire, {"p_regulada_bar": 6.0})
        assert m.tipo == c.neumatico.tipo, ref
        vistos.add(m.tipo)
        assert all(re.fullmatch(r"-X1\.\w+", n) for n in m.senales()), ref
    assert vistos == {"cilindro", "frl", "valvula_corte"}


@pytest.mark.parametrize("ref,senales", [
    ("MOTOR-075", {"-X1.rpm", "-X1.par_Nm", "-X1.I_A"}),
    ("CONT-9A-24VDC", {"-X1.cerrado"}),
    ("GM-2.5-4A", {"-X1.disparado", "-X1.termico_pct"}),
    ("VFD-2K2-220", {"-X1.f_Hz", "-X1.estado", "-X1.falla"}),
    ("FOTO-M18", {"-X1.activo"}),
    ("PLC-14DI-10DO-24VDC", {"-X1.%IX0.0", "-X1.%QX0.0", "-X1.%IW0"}),
])
def test_senales_con_los_nombres_de_d10(ref, senales):
    m = crear_modelo("-X1", ref, CATALOG[ref].electrico.modelo, ajustes_minimos(CATALOG[ref].electrico.modelo))
    assert senales <= set(m.senales()), ref


def test_tipo_y_listas_no_son_ajustes():
    sel = CATALOG["SEL-22-3POS-2NA"].electrico.modelo
    with pytest.raises(ValueError, match="no tiene el ajuste «tipo»"):
        validar_ajustes({"tipo": "pulsador"}, CATALOG["GM-2.5-4A"].electrico.modelo, "GM-2.5-4A")
    with pytest.raises(ValueError, match="no tiene el ajuste «posiciones»"):
        validar_ajustes({"posiciones": ["0"]}, sel, "SEL-22-3POS-2NA")
    assert validar_ajustes({"Ir_A": 3.2}, CATALOG["GM-2.5-4A"].electrico.modelo, "GM") == {"Ir_A": 3.2}
    assert validar_ajustes({"i": 40, "eta_reductor": 0.7}, CATALOG["NMRV-090"].electrico.modelo, "NMRV")
    assert validar_ajustes({"acel_s": 3}, CATALOG["VFD-2K2-220"].electrico.modelo, "VFD") == {"acel_s": 3}


# ── la red monofásica de verdad (D15) ────────────────────────────────────────────────────────


def test_tension_2f_dos_fases_sin_neutro():
    t = parse_tension("220 VAC 2F 60 Hz")
    assert t.fases == 2 and not t.neutro and t.linea == 220
    assert polos_validos(t) == ("L1", "L2", "PE")
    assert tension_entre(t, "L1", "L2") == pytest.approx(220)
    assert tension_entre(t, "L1", "PE") is None  # sin neutro, a tierra no se infiere
    red = CATALOG["RED-2F-220V-60HZ"].electrico
    assert red.fuentes[0].tension.fases == 2 and red.modelo["sistema"] == "2F"
    assert CATALOG["RED-1F-220V-60HZ"].electrico.modelo["sistema"] == "1F+N"
    assert {r for r, f in fichas().items() if f.modelo.get("tipo") == "red"} == {
        "RED-3F-220V-60HZ", "RED-3F-380-220V-60HZ", "RED-2F-220V-60HZ", "RED-1F-220V-60HZ"}


# ── el loader valida el bloque `modelo` ──────────────────────────────────────────────────────

_BASE = {"funcion": "F", "simbolo": "x", "montaje": "din",
         "bornes": [{"id": "1", "rol": "potencia"}, {"id": "2", "rol": "potencia"}]}


def _cargar(tmp_path, modelo: dict, **extra):
    from apolo.library.electrico.ficha_datos import requeridos

    # los datos de ficha que pide el tipo, sin valor (plan datos-de-corte-y-acometida, D4)
    datos = {"a_confirmar": list(requeridos(modelo.get("tipo"), _BASE["montaje"])), "fuente": "prueba"}
    comp = {"ref": "R", "name": "Prueba", "builder": "box", "weight": 1,
            "params": {"width": 18, "depth": 70, "height": 90},
            "electrico": {**_BASE, "modelo": modelo, **datos, **extra}}
    (tmp_path / "a.yaml").write_text(yaml.safe_dump({"category": "x", "components": [comp]}, allow_unicode=True),
                                     encoding="utf-8")
    return load_catalog(str(tmp_path))["R"].electrico


def test_la_clase_entra_en_una_sola_forma(tmp_path):
    assert _cargar(tmp_path, {"tipo": "guardamotor", "clase": 10}).modelo["clase"] == "10"
    assert _cargar(tmp_path, {"tipo": "rele_termico", "clase": "10A"}).modelo["clase"] == "10A"


@pytest.mark.parametrize("modelo,extra,mensaje", [
    ({"tipo": "guardamotr"}, {}, r"modelo\.tipo: «guardamotr» no es válido.*¿Quisiste decir «guardamotor»"),
    ({"tipo": "guardamotor", "clase": 15}, {}, r"modelo\.clase: «15» no es válido"),
    ({"tipo": "itm", "curva": "K"}, {}, r"modelo\.curva: «K» no es válido"),
    ({"tipo": "fusible", "cartucho_curva": "X"}, {}, r"modelo\.cartucho_curva: «X» no es válido"),
    ({"tipo": "guardamotor", "Ir_A": [4, 2.5]}, {}, r"modelo\.Ir_A: un rango es \[mín, máx\]"),
    ({"tipo": "red", "sistema": "3F"}, {"fuentes": [{"polos": {"1": "L1", "2": "L2"}, "tension": "220 VAC 2F"}]},
     r"modelo\.sistema: «3F» no es el de su fuente"),
    ({"tipo": "red"}, {}, r"modelo\.sistema: «None» no es válido"),
])
def test_un_modelo_mal_escrito_no_carga(tmp_path, modelo, extra, mensaje):
    with pytest.raises(ValueError, match=r"Componente 'R': electrico") as exc:
        _cargar(tmp_path, modelo, **extra)
    assert re.search(mensaje, str(exc.value)), str(exc.value)
