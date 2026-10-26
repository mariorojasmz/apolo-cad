"""El dispositivo dice su símbolo y quién lo mueve, sin mover la firma (plan pedidos-de-extensiones,
F2: D3, D4, D5).

  - `Dispositivo.simbolo`: el de su ficha eléctrica; un aparato sólo de aire, el de la neumática;
  - `Dispositivo.acoplado_a`: la regla única de `library/electrico/acoples.py` (la de la
    co-simulación), que el carril aplica al cerrar el modelo y `services/cosim_red.py` lee;
  - la firma del documento no ve ninguno de los dos (`escenarios.FUERA_DE_FIRMA`) y el trinquete
    obliga a decidir por cada campo nuevo de `Dispositivo`.
"""

from __future__ import annotations

import dataclasses

import pytest

from apolo.doc.document import Document
from apolo.library.catalog import CATALOG
from apolo.library.electrico import acoples
from apolo.library.electrico.modelo import Dispositivo
from apolo.services import escenarios
from apolo.services.cosim_red import entrada_red_documento
from apolo.services.escenarios import FUERA_DE_FIRMA, firma_documento
from tablero_electrico import (
    arranque_directo,
    arranque_variador_plc,
    arranque_variador_plc_cat3,
    arranque_variador_rele_seguridad,
    dev,
)


def _doc(cmds: list[dict], nombre: str = "f2") -> Document:
    d = Document(nombre)
    d.execute_many(cmds)
    return d


def _por_des(doc: Document) -> dict[str, Dispositivo]:
    return {d.designacion: d for d in doc.electrico.dispositivos}


# ── D4: quién mueve el bloque auxiliar ───────────────────────────────────────────────────────


def test_el_bloque_auxiliar_dice_que_lo_mueve_su_contactor():
    disp = _por_des(_doc(arranque_directo()))
    assert disp["-Q3A"].acoplado_a == "-Q3"
    assert all(d.acoplado_a is None for des, d in disp.items() if des != "-Q3A")


def test_la_co_simulacion_lee_el_acople_del_dispositivo():
    """El contacto de -Q3A sigue a la bobina de -Q3 por lo que dice el dispositivo, no por una
    cuenta propia: con otro `acoplado_a` la rama cambia de actuador."""
    from apolo.services.cosim_red import entrada_red

    m = _doc(arranque_directo()).electrico
    ramas = [r for r in entrada_red(m)["ramas"] if r.get("dispositivo") == "-Q3A"]
    assert ramas and {r["actuador"] for r in ramas} == {"-Q3.bobina"}
    otro = tuple(dataclasses.replace(d, acoplado_a="-Q2") if d.designacion == "-Q3A" else d
                 for d in m.dispositivos)
    ramas = [r for r in entrada_red(dataclasses.replace(m, dispositivos=otro))["ramas"]
             if r.get("dispositivo") == "-Q3A"]
    assert {r["actuador"] for r in ramas} == {"-Q2.cerrado"}  # el guardamotor: su protección


@pytest.mark.parametrize("cmds, buscado", [
    ([dev("CONT-AUX-1NA1NC", "-Q9A")], "-Q9"),  # no hay aparato -Q9
    ([dev("PILOTO-24V-VERDE", "-P9"), dev("CONT-AUX-1NA1NC", "-P9A")], "-P9"),  # -P9 no mueve nada
])
def test_sin_aparato_que_lo_mueva_queda_en_reposo_con_el_mismo_aviso(cmds, buscado):
    doc = _doc(cmds)
    aux = next(d for d in doc.electrico.dispositivos if acoples.es_bloque_auxiliar(d))
    assert aux.acoplado_a is None
    e = entrada_red_documento(doc)
    contactos = sum(c.accion == "acople" for c in aux.caminos)  # uno por contacto (NA y NC), como antes
    assert contactos == 2 and e["avisos"] == [
        f"{aux.designacion}: contacto auxiliar sin aparato que lo mueva (se busca «{buscado}»); "
        "queda en reposo"] * contactos
    assert e["actuadores"][f"{aux.designacion}.acople"] is False


def test_la_regla_pura():
    """Sufijo de letras tras un dígito; el maestro con bobina, protección o manija."""
    m = _doc(arranque_directo()).electrico
    por = {d.designacion: d for d in m.dispositivos}
    assert acoples.maestro_buscado("-Q3A") == "-Q3" and acoples.maestro_buscado("-Q3") == "-Q3"
    assert acoples.maestro_buscado("=Faja1-Q3AB") == "=Faja1-Q3"
    assert acoples.actuador_maestro(por["-Q3"]) == "bobina"
    assert acoples.actuador_maestro(por["-Q2"]) == "cerrado"
    assert acoples.actuador_maestro(por["-Q1"]) == "mano"
    assert acoples.actuador_maestro(por["-P1"]) is None
    assert acoples.acoplado_a(por["-Q3"], por) is None  # no es bloque auxiliar
    assert [d.acoplado_a for d in acoples.cerrar_acoples(m.dispositivos)] == [
        d.acoplado_a for d in m.dispositivos]


# ── D3: el símbolo ───────────────────────────────────────────────────────────────────────────


def test_el_simbolo_sale_de_la_ficha_electrica():
    for d in _doc(arranque_directo()).electrico.dispositivos:
        assert d.simbolo and d.simbolo == CATALOG[d.ref].electrico.simbolo, d.designacion


def test_un_aparato_de_aire_toma_el_simbolo_de_su_ficha():
    """Sólo de aire (el FRL): el ISO 1219-1 de la neumática; con bobinas (la electroválvula): el
    de su ficha eléctrica, como todo aparato con bornes."""
    doc = _doc([dev("FR-G14", ajustes={"p_regulada_bar": 6}), dev("VAL-52-MONO-G18")])
    por_ref = {d.ref: d for d in doc.electrico.dispositivos}
    frl, val = por_ref["FR-G14"], por_ref["VAL-52-MONO-G18"]
    assert CATALOG["FR-G14"].electrico is None
    assert frl.simbolo and frl.simbolo == CATALOG["FR-G14"].neumatico.simbolo
    assert val.simbolo and val.simbolo == CATALOG["VAL-52-MONO-G18"].electrico.simbolo


# ── D5: la firma no se mueve ─────────────────────────────────────────────────────────────────

#: Los campos de `Dispositivo` que SÍ entran a la firma del documento. Un campo nuevo va aquí
#: (vence todo resultado guardado con tablero) o en `escenarios.FUERA_DE_FIRMA` (no es física o
#: se deriva de lo que el log ya firma): el trinquete obliga a decidir.
EN_FIRMA = (
    "designacion", "ref", "funcion", "bornes", "caminos", "cargas", "fuentes", "ubicacion", "ajustes",
    "pieza", "modelo", "protege_motor", "parada_emergencia", "bornera", "id", "cantidad", "deducidos",
    "puertos", "neumatico", "servicio",
)


def test_todo_campo_del_dispositivo_esta_en_la_firma_o_fuera_de_ella():
    campos = {f.name for f in dataclasses.fields(Dispositivo)}
    assert not set(EN_FIRMA) & set(FUERA_DE_FIRMA)
    nuevos = campos - set(EN_FIRMA) - set(FUERA_DE_FIRMA)
    assert not nuevos, (f"campo(s) nuevo(s) de Dispositivo sin decidir: {sorted(nuevos)}. Si es física, "
                        "va a EN_FIRMA (vence todo resultado con tablero); si no, a "
                        "services/escenarios.FUERA_DE_FIRMA")
    assert not (set(EN_FIRMA) | set(FUERA_DE_FIRMA)) - campos, "un campo listado ya no existe"


def test_la_firma_lleva_exactamente_los_campos_en_firma():
    doc = _doc(arranque_directo())
    dispositivos, _, _ = escenarios._fichas_electricas(doc)
    assert dispositivos and all(set(d) == set(EN_FIRMA) for d in dispositivos)


#: Las firmas de los cuatro tableros, medidas en ec4ac9b (antes de `simbolo` y `acoplado_a`):
#: si cambian, todo resultado guardado de un documento con tablero queda vencido. Las tres del
#: variador se re-midieron al cambiar su LOG (sobre aa88ee5: PE en estrella y `STO_categoria`, reglas
#: «PE en cadena» y «canales del STO»); con el log de antes dan las de antes (`STO_canales` de
#: la ficha no entra: `test_sto_canales_no_entra_a_la_firma`). Las cuatro se re-midieron cuando la red
#: de 220 V de Lima declaró `esquema: IT` en su `modelo` (plan datos-de-corte-y-acometida § «Red de
#: 220 V de Lima: IT»): lo que la co-simulación lee de la ficha entra a la firma, así que todo resultado
#: guardado con esa red queda vencido (re-correrlo es barato); sin el esquema dan las de antes
#: (`test_la_firma_sin_el_it_de_la_red_es_la_de_antes`).
FIRMAS_SIN_IT = {"arranque_directo": "2:7feece8fd5f7af21a86c",
                 "arranque_variador_plc": "2:76116a74eca53a6fb0a3",
                 "arranque_variador_plc_cat3": "2:7c7b1ce05dbd21c3ddbb",
                 "arranque_variador_rele_seguridad": "2:62856d21257f95c61187"}
FIRMAS = {
    "arranque_directo": (arranque_directo, "2:28769e6dfe42c7388ca3"),
    "arranque_variador_plc": (arranque_variador_plc, "2:5171b7878826a436170d"),
    "arranque_variador_plc_cat3": (arranque_variador_plc_cat3, "2:e3dd3c514ac2f5006cd0"),
    "arranque_variador_rele_seguridad": (arranque_variador_rele_seguridad, "2:c726c9f8ede629298f74"),
}


@pytest.mark.parametrize("nombre", list(FIRMAS))
def test_la_firma_de_los_cuatro_tableros_no_se_mueve(nombre):
    cmds, firma = FIRMAS[nombre]
    assert firma_documento(_doc(cmds(), nombre)) == firma


def test_la_firma_sin_el_it_de_la_red_es_la_de_antes(monkeypatch):
    """Lo ÚNICO que movió las cuatro firmas es el `esquema: IT` de la red de Lima (los `datos` de la
    norma del lugar no entran: `test_los_datos_de_ficha_no_entran_a_la_firma_del_documento`)."""
    for ref in ("RED-3F-220V-60HZ", "RED-2F-220V-60HZ"):
        c = CATALOG[ref]
        modelo = {k: v for k, v in c.electrico.modelo.items() if k != "esquema"}
        monkeypatch.setitem(CATALOG, ref, dataclasses.replace(
            c, electrico=dataclasses.replace(c.electrico, modelo=modelo)))
    for nombre, (cmds, _firma) in FIRMAS.items():
        assert firma_documento(_doc(cmds(), nombre)) == FIRMAS_SIN_IT[nombre], nombre


def test_sto_canales_no_entra_a_la_firma(monkeypatch):
    """La lista de canales del STO la lee el ERC, no la co-simulación (`FUERA_DE_FIRMA_MODELO`):
    sumarla al YAML no vence los resultados guardados de un tablero con variador."""
    con = firma_documento(_doc(arranque_variador_plc(), "sto"))
    modelo = CATALOG["VFD-2K2-220"].electrico.modelo
    assert modelo["STO_canales"] == ["S1", "S2"]
    monkeypatch.delitem(modelo, "STO_canales")
    assert firma_documento(_doc(arranque_variador_plc(), "sto")) == con
