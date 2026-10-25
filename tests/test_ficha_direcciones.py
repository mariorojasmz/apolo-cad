"""Direcciones del fabricante en la ficha eléctrica (plan plc-en-el-lazo, D3): `electrico.direcciones`
opcional y COMPLETO, con `fuente`, validado al cargar (`ficha_direcciones.py`), publicado en el
catálogo, fuera de `modelo` (la firma del documento no se mueve), y el PLC del catálogo con las
direcciones por defecto de la CPU de su línea de referencia leídas en el manual del fabricante.
"""

from __future__ import annotations

import dataclasses

import pytest
import yaml

from apolo.library.catalog import CATALOG, catalog_payload
from apolo.library.electrico.ficha import ficha_payload
from apolo.library.electrico.ficha_direcciones import entradas_salidas
from apolo.library.loader import load_catalog

#: Un PLC de prueba chico: 2 DI, 1 DO y 1 AI, con su común y su alimentación.
PLC = {
    "funcion": "K", "simbolo": "plc", "montaje": "din",
    "bornes": [{"id": i, "rol": "mando" if i in ("L+", "M") else "señal"}
               for i in ("L+", "M", "1M", "I0.0", "I0.1", "Q0.0", "AI0")],
    "cargas": [{"bornes": ["L+", "M"], "tension": "24 VDC", "tipo": "alimentacion", "polar": True}],
    "modelo": {"tipo": "plc", "DI": 2, "DO": 1, "AI": 1},
    "datos": {"T_max_C": 55},
    "fuente": "ficha de prueba",
    "direcciones": {"I0.0": "%I0.0", "I0.1": "%I0.1", "Q0.0": "%Q0.0", "AI0": "%IW64"},
}


def _cargar(tmp_path, electrico: dict, ref: str = "R"):
    comp = {"ref": ref, "name": "Prueba", "builder": "box", "weight": 1,
            "params": {"width": 54, "depth": 75, "height": 90}, "electrico": electrico}
    (tmp_path / "a.yaml").write_text(yaml.safe_dump({"category": "x", "components": [comp]}, allow_unicode=True),
                                     encoding="utf-8")
    return load_catalog(str(tmp_path))[ref].electrico


def _con(**cambios) -> dict:
    out = {**PLC, **cambios}
    return {k: v for k, v in out.items() if v is not None}


def _dir(**cambios) -> dict:
    d = {**PLC["direcciones"], **cambios}
    return {k: v for k, v in d.items() if v is not None}


def test_las_e_s_son_los_bornes_que_el_st_alcanza_por_direccion():
    assert entradas_salidas(("L+", "M", "1M", "I0.0", "I1.7", "Q0.0", "AI0", "AQ1", "I0.8", "DI1", "PE")) == (
        "I0.0", "I1.7", "Q0.0", "AI0", "AQ1")


def test_un_mapa_completo_carga_en_el_orden_de_los_bornes_y_se_publica(tmp_path):
    f = _cargar(tmp_path, _con(direcciones={"AI0": " %IW64 ", "Q0.0": "%Q0.0", "I0.1": "%I0.1", "I0.0": "%I0.0"}))
    assert list(f.direcciones.items()) == [("I0.0", "%I0.0"), ("I0.1", "%I0.1"), ("Q0.0", "%Q0.0"),
                                           ("AI0", "%IW64")]
    p = ficha_payload(f)
    assert p["direcciones"]["AI0"] == "%IW64" and "direcciones" not in p["modelo"]
    assert "direcciones" not in f.modelo


def test_sin_direcciones_carga_igual_que_antes(tmp_path):
    f = _cargar(tmp_path, _con(direcciones=None))
    assert f.direcciones == {} and "direcciones" not in ficha_payload(f)


def test_lo_que_falta_va_en_a_confirmar_sin_valor(tmp_path):
    f = _cargar(tmp_path, _con(direcciones=None, a_confirmar=["direcciones"]))
    assert f.direcciones == {} and f.a_confirmar == ("direcciones",)
    assert ficha_payload(f)["a_confirmar"] == ["direcciones"]


@pytest.mark.parametrize(("bloque", "mensaje"), [
    (_con(direcciones=_dir(AI0=None)), r"direcciones: faltan AI0: el mapa cubre TODAS las E/S"),
    (_con(direcciones=_dir(I0_0="x")), r"el borne «I0_0» no existe.*¿Quisiste decir «I0.0»"),
    (_con(direcciones=_dir(**{"L+": "%L"})), r"«L\+» no es una E/S \(sólo se mapean I0.0 … AI0\)"),
    (_con(direcciones=_dir(**{"I0.0 ": "%I9.9"})), r"el borne «I0.0» está dos veces"),
    (_con(direcciones=_dir(AI0="")), r"direcciones.AI0: se espera la dirección como texto"),
    (_con(direcciones=_dir(AI0=64)), r"direcciones.AI0: se espera la dirección como texto"),
    (_con(direcciones=_dir(**{"I0.1": "%I0.0"})), r"«%I0.0» ya es de «I0.0»"),
    (_con(direcciones={}), r"direcciones: se espera un mapa \{borne: dirección del fabricante\}"),
    (_con(direcciones=["%I0.0"]), r"direcciones: se espera un mapa"),
    (_con(a_confirmar=["direcciones"]), r"está también en `a_confirmar`: lo que se confirma va SIN valor"),
    (_con(montaje="campo", datos=None, fuente=None),r"electrico.fuente: falta: con `direcciones` va de dónde salen"),
    (_con(a_confirmar=["direcciones", "direcciones"], direcciones=None), r"clave repetida"),
])
def test_un_mapa_mal_escrito_o_incompleto_no_carga(tmp_path, bloque, mensaje):
    with pytest.raises(ValueError, match=r"Componente 'R': electrico\.") as e:
        _cargar(tmp_path, bloque)
    assert e.match(mensaje), str(e.value)


def test_una_ref_sin_e_s_no_lleva_direcciones(tmp_path):
    rele = {"funcion": "K", "simbolo": "rele", "montaje": "din",
            "bornes": [{"id": "A1", "rol": "bobina"}, {"id": "A2", "rol": "bobina"}],
            "fuente": "ficha de prueba", "datos": {"T_max_C": 55}}
    with pytest.raises(ValueError, match=r"no tiene E/S que el ST alcance por dirección"):
        _cargar(tmp_path, {**rele, "direcciones": {"A1": "%I0.0"}})
    with pytest.raises(ValueError, match=r"«direcciones» no es un dato de esta ficha"):
        _cargar(tmp_path, {**rele, "a_confirmar": ["direcciones"]})


def test_el_plc_del_catalogo_trae_las_direcciones_de_su_linea_de_referencia_con_su_fuente():
    """La CPU de la línea de referencia, por defecto (manual de sistema del fabricante, bitácora
    F1a): DI en los bytes 0…1, DQ en 0…1, AI en 64…67 de a 2 bytes por canal."""
    f = CATALOG["PLC-14DI-10DO-24VDC"].electrico
    di = [f"I{i // 8}.{i % 8}" for i in range(14)]
    dq = [f"Q{i // 8}.{i % 8}" for i in range(10)]
    assert f.direcciones == {**{b: f"%{b}" for b in di + dq}, "AI0": "%IW64", "AI1": "%IW66"}
    assert set(f.direcciones) == set(entradas_salidas(f.ids_bornes))
    assert "direcciones" not in f.a_confirmar
    assert "Addressing the local and expansion I/O" in f.fuente and "11/2024" in f.fuente
    # el ST de Apolo sigue con sus direcciones (V8.3 D4): el modelo no las conoce
    assert "direcciones" not in f.modelo
    plc = next(c for c in catalog_payload() if c["ref"] == "PLC-14DI-10DO-24VDC")
    assert plc["electrico"]["direcciones"]["AI1"] == "%IW66"


def test_toda_ref_del_catalogo_con_direcciones_las_trae_completas():
    for ref, comp in CATALOG.items():
        f = comp.electrico
        if f is not None and f.direcciones:
            assert list(f.direcciones) == list(entradas_salidas(f.ids_bornes)), ref
            assert f.fuente, ref


def test_las_direcciones_no_entran_a_la_firma_del_documento(monkeypatch):
    """Con los mismos comandos, quitar las direcciones de todas las fichas da la MISMA firma en los 4
    tableros del banco: no llegan a `Dispositivo` (antes/después, en la bitácora)."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from tablero_electrico import (
        arranque_directo,
        arranque_variador_plc,
        arranque_variador_plc_cat3,
        arranque_variador_rele_seguridad,
    )

    from apolo.doc.document import Document
    from apolo.services.escenarios import firma_documento

    tableros = (arranque_directo, arranque_variador_plc, arranque_variador_plc_cat3,
                arranque_variador_rele_seguridad)

    def firmas() -> list[str]:
        out = []
        for t in tableros:
            d = Document("firma")
            d.execute_many(t())
            out.append(firma_documento(d))
        return out

    con = firmas()
    for ref, comp in list(CATALOG.items()):
        f = comp.electrico
        if f is not None and f.direcciones:
            monkeypatch.setitem(CATALOG, ref, dataclasses.replace(comp, electrico=dataclasses.replace(f, direcciones={})))
    assert firmas() == con
