"""Reglas del ERC sobre el camino de la protección (`library/electrico/erc_seguridad.py`).

  - «PE en cadena» (IEC 60204-1 §8.2.3): un `add_wire` de tierra que pasa por los bornes PE de
    los aparatos (-X0:1 → -T1:PE → -T2:PE → -K1:PE → -X0:2) da ERROR: retirar -T2 deja sin tierra
    a -K1. En estrella, o con el PE del cable del motor en el borne del variador, sin error.
  - «canales del STO» (ISO 13849-1): S1 y S2 del variador en la misma red (un solo contacto los
    alimenta) dan AVISO sin categoría declarada, ERROR con `STO_categoria` 3 o 4 y ok con B, 1 o 2;
    en redes propias (seta de dos NC) o con el puente de fábrica a +24 V, sin hallazgo.
"""

from __future__ import annotations

import dataclasses

import pytest

from apolo.library.catalog import CATALOG
from apolo.library.electrico.ajustes import validar_ajustes
from apolo.library.electrico.erc import erc, resumen
from apolo.library.electrico.ficha import parse_ficha
from test_electrico_erc import _con, _idx, arranque_variador, disp, w

PE = dict(color="GNYE")
BU = dict(color="BU", seccion=0.75)


def _filas(reglas: list[dict], regla: str) -> list[dict]:
    return [r for r in reglas if r["regla"] == regla]


def _con_vfd(modelo, **ajustes):
    """El tablero (b) con otros ajustes en -T2 (sin `STO_categoria` si no se pasa)."""
    dispositivos = tuple(dataclasses.replace(d, ajustes=dict(ajustes)) if d.designacion == "-T2" else d
                         for d in modelo.dispositivos)
    return dataclasses.replace(modelo, dispositivos=dispositivos)


def _estrella(m):
    return [_idx(m, "-X0:1", p) for p in ("-T2:PE", "-T1:PE", "-K1:PE", "-U1:PE")]


# ── PE en cadena ──────────────────────────────────────────────────────────────────────────


def test_pe_en_cadena_por_los_bornes_de_los_aparatos_es_error():
    m = arranque_variador()
    cadena = w("-X0:1", "-T1:PE", "-T2:PE", "-K1:PE", "-X0:2", **PE)
    m = dataclasses.replace(_con(m, quitar=tuple(_estrella(m)), agregar=(cadena,)),
                            dispositivos=tuple(disp("-X0", "BORNE-PE-4", cantidad=2) if d.designacion == "-X0"
                                               else d for d in m.dispositivos))
    # el gabinete, a la bornera aparte (no es parte de la cadena)
    m = _con(m, agregar=(w("-X0:1", "-U1:PE", **PE),))
    reglas = erc(m)
    malas = [r for r in reglas if r["estado"] == "error"]
    assert [r["regla"] for r in malas] == ["PE en cadena", "PE en cadena"], malas
    t2, t1 = malas  # en el orden de los dispositivos del modelo
    # el motor cuelga del PE de -T2 por su cable (eso vale), y -T2 cuelga de -T1: retirar -T1 lo
    # deja sin tierra también
    assert t1["detalle"].startswith("-T1 (FUENTE-24VDC-5A): su borne de tierra -T1:PE es paso de la tierra "
                                    "de -T2, -M1, -K1 ")
    assert t2["detalle"].startswith("-T2 (VFD-2K2-220): su borne de tierra -T2:PE es paso de la tierra de -K1 ")
    assert "-X0:1 → -T1:PE → -T2:PE → -K1:PE → -X0:2" in t2["detalle"]
    assert "retirar -T2 los deja sin PE" in t2["detalle"]
    assert t2["elementos"] == ["-T2:PE", "-K1:PE"]
    assert "su propio conductor PE hasta la barra o bornera de tierra" in t2["recomendacion"]
    assert t2["norma"].startswith("IEC 60204-1 §8.2.3")
    # -K1 va al final de la cadena: retirarlo no deja a nadie sin tierra
    assert not any(r["detalle"].startswith("-K1") for r in malas)
    assert resumen(reglas)["estado"] == "error"


def test_pe_de_aparato_a_aparato_en_conductores_sueltos_tambien_es_cadena():
    m = arranque_variador()
    m = _con(m, cambiar={_idx(m, "-X0:1", "-K1:PE"): w("-T1:PE", "-K1:PE", **PE)})
    malas = [r for r in erc(m) if r["estado"] != "ok"]
    assert [r["regla"] for r in malas] == ["PE en cadena"]
    assert malas[0]["detalle"].startswith("-T1 (FUENTE-24VDC-5A): su borne de tierra -T1:PE es paso de la tierra de -K1 ")
    assert "conductor" in malas[0]["detalle"] and "-T1:PE → -K1:PE" in malas[0]["detalle"]


def test_pe_en_estrella_y_el_pe_del_cable_del_motor_en_el_variador_quedan_ok():
    """La versión correcta del tablero (b): cada aparato con su conductor a -X0:1; el motor toma
    el PE del cable -W1 que sale del variador (-T2:PE → -M1:PE), como pide su manual."""
    fila, = _filas(erc(arranque_variador()), "PE en cadena")
    assert fila["estado"] == "ok"
    assert fila["detalle"].startswith("Los 6 aparatos con borne de tierra llegan al PE por su propio conductor")


def test_dos_conductores_pe_al_mismo_aparato_no_son_cadena():
    m = arranque_variador()
    fila, = _filas(erc(_con(m, agregar=(w("-X0:1", "-T2:PE", **PE),))), "PE en cadena")
    assert fila["estado"] == "ok"


def test_pe_del_motor_por_un_conductor_suelto_desde_el_variador_es_cadena():
    """La excepción es el hilo PE del CABLE que el variador alimenta, no cualquier conductor."""
    m = arranque_variador()
    m = _con(m, cambiar={_idx(m, "-T2:PE", "-M1:PE"): w("-T2:PE", "-M1:PE", **PE)})
    malas = [r for r in erc(m) if r["regla"] == "PE en cadena" and r["estado"] == "error"]
    assert len(malas) == 1 and "es paso de la tierra de -M1 " in malas[0]["detalle"]


# ── canales del STO ───────────────────────────────────────────────────────────────────────


def test_sto_con_los_dos_canales_puenteados_sin_categoria_es_aviso():
    reglas = erc(_con_vfd(arranque_variador()))
    fila, = _filas(reglas, "canales del STO")
    assert fila["estado"] == "aviso"
    assert fila["detalle"].startswith("-T2 (VFD-2K2-220): los canales S1, S2 del STO están en la misma red")
    assert "-S0:12" in fila["detalle"] and "el lazo no declara su categoría" in fila["detalle"]
    assert fila["elementos"] == ["-T2:S1", "-T2:S2"]
    assert '{"STO_categoria": 1}' in fila["recomendacion"]
    assert fila["norma"].startswith("ISO 13849-1")
    assert resumen(reglas) == {"estado": "aviso", "errores": 0, "avisos": 1}


@pytest.mark.parametrize("categoria", [3, 4])
def test_sto_puenteado_con_categoria_3_o_4_declarada_es_error(categoria):
    fila, = _filas(erc(_con_vfd(arranque_variador(), STO_categoria=categoria)), "canales del STO")
    assert fila["estado"] == "error"
    assert fila["detalle"].endswith(f"y el lazo declara categoría {categoria}.")
    assert "cada canal por su propio contacto" in fila["recomendacion"]


@pytest.mark.parametrize("categoria", ["B", 1, 2])
def test_sto_puenteado_con_categoria_baja_declarada_queda_ok(categoria):
    fila, = _filas(erc(_con_vfd(arranque_variador(), STO_categoria=categoria)), "canales del STO")
    assert fila["estado"] == "ok" and f"declara categoría {categoria}" in fila["detalle"]


def test_el_caso_medido_con_el_plc_en_el_mismo_potencial():
    """-K1:I0.2 -S6:12 -T2:S1 -T2:S2: la seta -S6 alimenta los dos canales y la entrada del PLC."""
    m = arranque_variador()
    seta = disp("-S6", "ESTOP-40")
    m = dataclasses.replace(_con(m, cambiar={_idx(m, "-S0:12", "-T2:S1"): w("-S0:12", "-K1:I0.1", **BU)},
                                 agregar=(w("-T1:L+", "-S6:11", **BU),
                                          w("-K1:I0.2", "-S6:12", "-T2:S1", "-T2:S2", **BU))),
                            dispositivos=_con_vfd(m, STO_categoria=3).dispositivos + (seta,))
    m = _con(m, quitar=(_idx(m, "-S1:14", "-K1:I0.2"),), agregar=(w("-S1:14", "-K1:I0.5", **BU),))
    fila, = _filas(erc(m), "canales del STO")
    assert fila["estado"] == "error" and "-S6:12" in fila["detalle"]


def test_sto_con_un_contacto_por_canal_queda_ok():
    m = arranque_variador()
    seta = disp("-S0", "ESTOP-40-2NC")
    m = _con(m, cambiar={_idx(m, "-S0:12", "-T2:S1"): w("-S0:12", "-T2:S1", "-K1:I0.1", **BU)},
             agregar=(w("-T1:L+", "-S0:21", **BU), w("-S0:22", "-T2:S2", **BU)),
             dispositivos=tuple(seta if d.designacion == "-S0" else d
                                for d in _con_vfd(m, STO_categoria=3).dispositivos))
    reglas = erc(m)
    fila, = _filas(reglas, "canales del STO")
    assert fila["estado"] == "ok" and fila["detalle"] == "1 variador(es) con STO: cada canal en su propia red."
    assert resumen(reglas)["estado"] == "ok"


def test_sto_puenteado_a_24v_sin_contacto_no_es_de_esta_regla():
    """El puente de fábrica (S1 y S2 a +24 V): no hay parada por el STO; no se avisa."""
    m = arranque_variador()
    m = _con(m, cambiar={_idx(m, "-S0:12", "-T2:S1"): w("-S0:12", "-K1:I0.1", **BU)},
             agregar=(w("-T1:L+", "-T2:S1", "-T2:S2", **BU),))
    fila, = _filas(erc(_con_vfd(m)), "canales del STO")
    assert fila["estado"] == "ok"


def test_sin_variador_con_sto_no_hay_fila():
    from test_electrico_erc import arranque_directo

    assert not _filas(erc(arranque_directo()), "canales del STO")


# ── la ficha y el ajuste ──────────────────────────────────────────────────────────────────


def test_toda_ref_con_sto_declara_sus_canales():
    con_sto = [ref for ref, c in CATALOG.items() if c.electrico and c.electrico.modelo.get("STO") is True]
    assert con_sto, "el catálogo del núcleo tiene variadores con STO"
    for ref in con_sto:
        m = CATALOG[ref].electrico.modelo
        assert m.get("STO_canales") == ["S1", "S2"], ref


def test_sto_canales_con_un_borne_que_no_existe_no_carga():
    crudo = {"funcion": "T", "simbolo": "variador", "montaje": "placa",
             "bornes": [{"id": "S1", "rol": "señal"}, {"id": "S2", "rol": "señal"}],
             "modelo": {"tipo": "variador", "STO": True, "STO_canales": ["S1", "S3"]}}
    with pytest.raises(ValueError, match="el borne «S3» no existe"):
        parse_ficha(crudo, "VFD-X")
    with pytest.raises(ValueError, match="sin repetir"):
        parse_ficha({**crudo, "modelo": {"STO_canales": ["S1", "S1"]}}, "VFD-X")
    with pytest.raises(ValueError, match="≥ 2 bornes"):
        parse_ficha({**crudo, "modelo": {"STO_canales": ["S1"]}}, "VFD-X")


def test_el_ajuste_sto_categoria():
    modelo = CATALOG["VFD-2K2-220"].electrico.modelo
    assert validar_ajustes({"STO_categoria": 3}, modelo, "VFD-2K2-220") == {"STO_categoria": 3}
    assert validar_ajustes({"STO_categoria": "b"}, modelo, "VFD-2K2-220") == {"STO_categoria": "B"}
    with pytest.raises(ValueError, match="B, 1, 2, 3 o 4"):
        validar_ajustes({"STO_categoria": 5}, modelo, "VFD-2K2-220")
    with pytest.raises(ValueError, match="B, 1, 2, 3 o 4"):
        validar_ajustes({"STO_categoria": True}, modelo, "VFD-2K2-220")
    sin_sto = {k: v for k, v in modelo.items() if k not in ("STO", "STO_canales")}
    with pytest.raises(ValueError, match="no tiene entrada STO"):
        validar_ajustes({"STO_categoria": 3}, sin_sto, "VFD-X")
    # en otra clase de aparato no es un ajuste
    with pytest.raises(ValueError, match="no tiene el ajuste «STO_categoria»"):
        validar_ajustes({"STO_categoria": 3}, CATALOG["GM-2.5-4A"].electrico.modelo, "GM-2.5-4A")
