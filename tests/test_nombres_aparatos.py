"""El nombre por función de cada aparato (plan nombres-por-funcion, F1): el dato declarado en
`add_device` (`rotulo`, `estados`, `descripcion`), su respaldo para MOSTRAR
(`services/nombres_aparatos.py`) y lo que suman la tabla del vivo, los paneles y el circuito.

- la cadena D3 con su `origen`: declarado → pieza → derivado (relé de seguridad) → tipo (A8);
- los estados por defecto de cada tipo y las claves de su ficha (A4);
- A11: lo que vigila un relé y lo que rearma un pulsador, por la CADENA SERIE;
- A15: la sugerencia de la pieza limpia antes de cortar;
- A5: `estados` estricto al entrar y tolerante al cargar (nunca suprime un aparato);
- lo derivado nunca es una designación sola ni un id de comando.
"""

from __future__ import annotations

import re

import pytest

from apolo.commands.errors import CommandError
from apolo.doc.document import Document
from apolo.library.electrico import estados as E
from apolo.services import escenarios
from apolo.services.electrico import circuito
from apolo.services.nombres_aparatos import (
    Nombres,
    humanizar,
    limpiar_nombre_pieza,
    nombre_junta,
    nombres_en_tabla,
    para_tabla,
)
from tablero_electrico import arranque_directo, dev, wire

BU = {"color": "BU", "seccion_mm2": 0.75}


def _doc(cmds: list[dict]) -> Document:
    d = Document("nombres")
    d.execute_many(cmds)
    return d


def mezcladora() -> list[dict]:
    """El mando de seguridad de la mezcladora, reducido: la seta -S0 y la tapa -B1 en serie en los
    dos canales de -K2; el recipiente -B4 en los de -K3; el rearme -S3 a S34 de los dos relés.
    S11, S21 y S33 van al +24 V con TODO el mando (como en la mezcladora): la red directa de S12
    sólo ve a -B1 (A11)."""
    return [
        dev("FUENTE-24VDC-5A", "-T1"), dev("SECC-25A-3P", "-Q1"), dev("ESTOP-40-2NC", "-S0"),
        dev("RESG-2NC", "-B1", "+CAMPO"), dev("RESG-2NC", "-B4", "+CAMPO"),
        dev("RS-2C-24VDC", "-K2"), dev("RS-2C-24VDC", "-K3"),
        dev("PULS-22-AZUL-NA", "-S3"), dev("PULS-22-VERDE-NA", "-S1"), dev("SEL-22-2POS-1NA", "-S4"),
        dev("PILOTO-24V-AMBAR", "-P3"),
        wire("-T1:L+", "-K2:S11", "-K2:S21", "-K2:S33", "-K3:S11", "-K3:S21", "-K3:S33", "-S0:11", "-S0:21",
             "-S3:13", "-S1:13", **BU),
        wire("-S0:12", "-B1:11", **BU), wire("-B1:12", "-K2:S12", **BU),
        wire("-S0:22", "-B1:21", **BU), wire("-B1:22", "-K2:S22", **BU),
        wire("-K3:S11", "-B4:11", **BU), wire("-B4:12", "-K3:S12", **BU),
        wire("-K3:S21", "-B4:21", **BU), wire("-B4:22", "-K3:S22", **BU),
        wire("-S3:14", "-K2:S34", "-K3:S34", **BU),
    ]


@pytest.fixture(scope="module")
def mezcla() -> Document:
    cmds = mezcladora()
    for c in cmds:
        if c["params"].get("designacion") == "-B1":
            c["params"]["rotulo"] = "Tapa del tanque"
        if c["params"].get("designacion") == "-B4":
            c["params"]["rotulo"] = "Recipiente bajo la descarga"
            c["params"]["estados"] = {"cerrado": "Acoplado", "abierto": "Sin recipiente"}
        if c["params"].get("designacion") == "-S3":
            c["params"]["rotulo"] = "Rearme de seguridad"
            c["params"]["descripcion"] = "Además borra la falla de la compuerta"
    return _doc(cmds)


# ── A11: la cadena serie ───────────────────────────────────────────────────────────────────


def test_el_rele_vigila_la_cadena_serie_no_la_red_directa(mezcla):
    n = Nombres(mezcla)
    assert n.vigila("-K2") == ["-S0", "-B1"]  # seta → tapa → K2: la red directa de S12 sólo ve -B1
    assert n.vigila("-K3") == ["-B4"]


def test_el_rearme_rearma_a_los_dos_reles(mezcla):
    n = Nombres(mezcla)
    assert n.rearma_a("-S3") == ["-K2", "-K3"]
    assert n.rearma_a("-S1") == [] and n.rearma_a("-S0") == []


def test_los_grupos_d11(mezcla):
    n = Nombres(mezcla)
    assert n.grupo_de("-Q1") == "energia"
    assert {des: n.grupo_de(des) for des in ("-S0", "-B1", "-B4", "-S3")} == dict.fromkeys(
        ("-S0", "-B1", "-B4", "-S3"), "seguridad")  # el rearme, por estar cableado a S34
    assert n.grupo_de("-S1") == "operacion" and n.grupo_de("-S4") == "operacion"
    assert n.grupo_de("-P3") == "pilotos" and n.grupo_de("-K2") == "lecturas"


# ── D3: la cadena del rótulo, con su origen ────────────────────────────────────────────────


def test_la_cadena_d3(mezcla):
    n = Nombres(mezcla)
    assert n.rotulo_de("-B1") == ("Tapa del tanque", "declarado")
    assert n.rotulo_de("-K2") == ("Seguridad de parada de emergencia y tapa del tanque", "derivado")
    assert n.rotulo_de("-K3") == ("Seguridad de recipiente bajo la descarga", "derivado")
    assert n.rotulo_de("-S1") == ("Pulsador verde", "tipo")
    assert n.rotulo_de("-P3") == ("Piloto ámbar", "tipo")


def test_a8_el_tipo_que_ya_es_su_funcion(mezcla):
    n = Nombres(mezcla)
    assert n.rotulo_de("-S0") == ("Parada de emergencia", "tipo")
    assert n.rotulo_de("-Q1") == ("Interruptor general", "tipo")


def test_la_pieza_escrita_por_alguien_gana_al_tipo():
    d = Document("pieza")
    caja = d.execute("create_box", {"name": "Interruptor de tapa -B1 (compra, Schmersal AZ 16)",
                                    "width": 40, "depth": 30, "height": 90})
    d.execute_many([dev("RESG-2NC", "-B1", "+CAMPO", pieza=caja), dev("RESG-2NC", "-B2", "+CAMPO")])
    n = Nombres(d)
    assert n.rotulo_de("-B1") == ("Interruptor de tapa", "pieza")
    assert n.rotulo_de("-B2") == ("Interruptor de resguardo", "tipo")


def test_el_rele_sin_nada_en_serie_cae_al_tipo():
    n = Nombres(_doc([dev("RS-2C-24VDC", "-K2")]))
    assert n.rotulo_de("-K2") == ("Relé de seguridad", "tipo")


def test_lo_derivado_nunca_es_una_designacion_ni_un_id(mezcla):
    """Toda fila: ni la designación sola, ni «c160», ni vacío."""
    for doc in (mezcla, _doc(arranque_directo())):
        n = Nombres(doc)
        for des in n.disp:
            r, origen = n.rotulo_de(des)
            assert r and origen in ("declarado", "pieza", "derivado", "tipo"), des
            assert r != des and not re.search(r"(?<!\w)c\d+(?!\w)", r), (des, r)
            assert not re.fullmatch(r"[-=+]?\w*-[A-Z]{1,3}\d+", r), (des, r)
        for nombre in n.ramas().values():
            assert not re.search(r"(?<!\w)c\d+(?!\w)", nombre), nombre


# ── estados: la tabla A4 y los defaults ────────────────────────────────────────────────────


def test_los_estados_por_defecto(mezcla):
    n = Nombres(mezcla)
    assert n.estados_de("-Q1") == {"cerrado": "Encendido", "abierto": "Apagado"}
    assert n.estados_de("-B1") == {"cerrado": "Cerrado", "abierto": "Abierto"}
    assert n.estados_de("-B4") == {"cerrado": "Acoplado", "abierto": "Sin recipiente"}
    assert n.estados_de("-S4") == {"0": "0", "I": "I"}  # la posición tal cual
    assert n.estados_de("-S1") == {} and n.estados_de("-P3") == {}


def test_la_tabla_de_claves_a4():
    assert E.claves({"tipo": "selector", "posiciones": ["I", "0", "II"]}) == ("I", "0", "II")
    assert E.claves({"tipo": "electrovalvula"}, {"tipo": "valvula", "vias": 5, "posiciones": 2}) == ("14", "12")
    assert E.claves({"tipo": "electrovalvula"}, {"tipo": "valvula", "vias": 5, "posiciones": 3}) == ("14", "0", "12")
    assert E.claves(None, {"tipo": "valvula", "vias": 3, "posiciones": 2}) == ("12", "0")
    assert E.claves({"tipo": "seccionador"}) == E.claves({"tipo": "resguardo"}) == ("cerrado", "abierto")
    assert E.claves({"tipo": "pulsador", "actuadores": ["marcha", "paro"]}) == ("marcha", "paro")
    assert E.claves({"tipo": "pulsador"}) == () and E.claves({"tipo": "piloto"}) == ()


def test_la_botonera_nombra_cada_actuador():
    n = Nombres(_doc([dev("BOTONERA-2", "-S1", "+CAMPO", estados={"paro": "Parada del ciclo"})]))
    assert n.estados_de("-S1") == {"marcha": "Marcha", "paro": "Parada del ciclo"}


def test_la_valvula_nombra_las_posiciones_del_carrete_y_entra_a_la_tabla():
    doc = _doc([dev("VAL-52-MONO-G18", "-QM1", "+CAMPO", rotulo="Válvula de la compuerta",
                    estados={"14": "Abre la compuerta", "12": "Cierra la compuerta"})])
    n = Nombres(doc)
    assert n.estados_de("-QM1") == {"14": "Abre la compuerta", "12": "Cierra la compuerta"}
    assert n.grupo_de("-QM1") == "operacion"  # la ficha trae accionamiento manual
    tabla = nombres_en_tabla({"valvulas": [{"designacion": "-QM1", "ref": "VAL-52-MONO-G18", "lados": ["14"],
                                            "manual": True}]}, para_tabla(doc))
    fila = tabla["valvulas"][0]
    assert fila["posiciones"] == ["14", "12"] and fila["lados"] == ["14"]
    assert fila["rotulo"] == "Válvula de la compuerta" and fila["origen"] == "declarado"


# ── A5: estricto al entrar, tolerante al cargar ────────────────────────────────────────────


def test_una_clave_que_la_ficha_no_tiene_se_rechaza_con_las_validas():
    d = Document("estricto")
    with pytest.raises(CommandError, match=r"«II».*«0», «I»"):
        d.execute("add_device", {"ref": "SEL-22-2POS-1NA", "designacion": "-S4", "estados": {"II": "Otro"}})
    with pytest.raises(CommandError, match="no tiene estados"):
        d.execute("add_device", {"ref": "PULS-22-VERDE-NA", "designacion": "-S1", "estados": {"x": "Marcha"}})
    assert not d.commands


def test_al_editar_se_valida_solo_si_cambian_los_estados_o_la_ref():
    d = Document("editar")
    cid = d.execute("add_device", {"ref": "SEL-22-2POS-1NA", "designacion": "-S4", "estados": {"0": "Manual"}})
    with pytest.raises(CommandError, match="«II»"):
        d.edit(cid, {"estados": {"II": "Otro"}}, merge=True)
    with pytest.raises(CommandError, match="no tiene estados"):  # otra ref, sin esa clave
        d.edit(cid, {"ref": "PULS-22-VERDE-NA"}, merge=True)
    d.commands[0]["params"]["estados"] = {"0": "Manual", "II": "vencida"}  # un catálogo que cambió
    d.edit(cid, {"rotulo": "Modo"}, merge=True)  # otro campo: no traba
    disp = d.electrico.dispositivos[0]
    assert disp.rotulo == "Modo" and disp.estados == {"0": "Manual"} and disp.estados_vencidos == ("II",)


@pytest.mark.parametrize("tolerante", [False, True])
def test_un_log_con_un_estado_vencido_abre_con_el_dispositivo(tolerante):
    d = Document("vencido")
    d.execute_many([dev("SEL-22-2POS-1NA", "-S4", estados={"0": "Manual", "I": "Ciclo"}),
                    dev("PULS-22-VERDE-NA", "-S1")])
    d.commands[0]["params"]["estados"] = {"0": "Manual", "I": "Ciclo", "II": "Mantenimiento"}
    d.commands[1]["params"]["estados"] = {"mano": "Marcha"}
    abierto = Document.from_apolo_bytes(d.to_apolo_bytes(), tolerant=tolerante)
    assert not getattr(abierto, "regen_suppressed", [])
    por = {x.designacion: x for x in abierto.electrico.dispositivos}
    assert set(por) == {"-S4", "-S1"}
    assert por["-S4"].estados == {"0": "Manual", "I": "Ciclo"} and por["-S4"].estados_vencidos == ("II",)
    assert por["-S1"].estados == {} and por["-S1"].estados_vencidos == ("mano",)
    fila = next(x for x in circuito(abierto)["dispositivos"] if x["designacion"] == "-S4")
    assert fila["estados_vencidos"] == ["II"] and "ya no tiene" in fila["aviso_estados"]
    abierto.execute("add_device", {"ref": "PILOTO-24V-VERDE", "designacion": "-P1"})  # la mutación sigue


# ── A6, D7 y A14 ───────────────────────────────────────────────────────────────────────────


def test_un_rotulo_que_empieza_con_igual_es_texto():
    d = _doc([dev("PULS-22-VERDE-NA", "-S1", rotulo="=Marcha", descripcion="=hola")])
    assert d.electrico.dispositivos[0].rotulo == "=Marcha"


def test_ponerle_nombre_no_vence_los_resultados():
    """D7: el rótulo, los estados y la descripción no entran a la firma de los escenarios."""
    antes = escenarios.firma_documento(_doc(mezcladora()))
    cmds = mezcladora()
    for c in cmds:
        if c["params"].get("designacion") == "-S4":
            c["params"].update(rotulo="Modo", estados={"0": "Manual"}, descripcion="Elige cómo trabaja")
    assert escenarios.firma_documento(_doc(cmds)) == antes


def test_el_circuito_suma_el_nombre_solo_si_esta_declarado(mezcla):
    filas = {x["designacion"]: x for x in circuito(mezcla)["dispositivos"]}
    assert filas["-S3"]["rotulo"] == "Rearme de seguridad"
    assert filas["-S3"]["descripcion"] == "Además borra la falla de la compuerta"
    assert filas["-B4"]["estados"] == {"cerrado": "Acoplado", "abierto": "Sin recipiente"}
    assert not {"rotulo", "estados", "descripcion", "estados_vencidos"} & set(filas["-S1"])


# ── A15, juntas, escenarios ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("nombre, des, esperado", [
    ("Interruptor de seguridad con bloqueo por solenoide puerta nivel 0 -B11 (compra, Schmersal AZM)",
     "-B11", "Interruptor de seguridad"),  # corta en palabra y sin conector colgando
    ("Interruptor de tapa -B1", "-B1", "Interruptor de tapa"),
    ("Mezcladora · Interruptor de recipiente acoplado (-B4)", "-B4", "Interruptor de recipiente"),
    ("Tablero de control +TAB1 · -S1", "-S1", ""),  # sin palabra: nada
    ("c66", "", ""),
    ("Sensor de nivel bajo", "-B2", "Sensor de nivel bajo"),
])
def test_a15_limpia_antes_de_cortar(nombre, des, esperado):
    assert limpiar_nombre_pieza(nombre, des) == esperado
    assert len(limpiar_nombre_pieza(nombre, des)) <= 30


def test_humanizar_y_juntas():
    assert humanizar("descargar_sin_recipiente") == "Descargar sin recipiente"
    assert humanizar("c388_puerta") == "Puerta"
    d = Document("juntas")
    base = d.execute("create_box", {"name": "Bastidor", "width": 100, "depth": 100, "height": 10})
    tapa = d.execute("create_box", {"name": "Mezcladora · Tapa de carga", "width": 100, "depth": 100,
                                    "height": 5, "position": {"x": 0, "y": 0, "z": 20}})
    d.execute("add_joint", {"name": "j_tapa_carga", "type": "giratoria", "parent": base, "child": tapa,
                            "origin": {"x": 0, "y": 50, "z": 20}, "axis": {"x": 1, "y": 0, "z": 0}})
    assert nombre_junta(d, "j_tapa_carga") == "Tapa de carga"
    assert nombre_junta(d, "no_existe") == "No existe"


# ── la tabla del vivo ──────────────────────────────────────────────────────────────────────


def test_la_tabla_del_vivo_suma_claves_sin_quitar_ninguna(mezcla):
    tabla = {"mandos": [{"designacion": "-S3", "tipo": "pulsador", "ref": "PULS-22-AZUL-NA"},
                        {"designacion": "-B4", "tipo": "resguardo", "ref": "RESG-2NC"}],
             "pilotos": [{"designacion": "-P3", "ref": "PILOTO-24V-AMBAR", "senal": "-P3.encendido"}],
             "fallas": [{"designacion": "-K2", "tipo": "rele_seguridad", "fallas": []}],
             "ramas": [{"id": "-K2:13-14", "tipo": "contacto", "red": "mando", "dispositivo": "-K2"},
                       {"id": "-W1.1#2", "tipo": "conductor", "red": "potencia"}],
             "juntas": [{"name": "j_x", "tipo": "hinge", "unidad": "grados"}]}
    nombres = para_tabla(mezcla)
    out = nombres_en_tabla(tabla, nombres)
    for lista, filas in tabla.items():
        for antes, despues in zip(filas, out[lista]):
            assert set(antes) <= set(despues) and all(despues[k] == v for k, v in antes.items())
    s3 = out["mandos"][0]
    assert s3["rotulo"] == "Rearme de seguridad" and s3["origen"] == "declarado"
    assert s3["rearma"] == ["-K2", "-K3"] and s3["grupo"] == "seguridad"
    assert s3["descripcion"] == "Además borra la falla de la compuerta"
    assert out["mandos"][1]["estados"] == {"cerrado": "Acoplado", "abierto": "Sin recipiente"}
    assert set(out["fallas"][0]) == {"designacion", "tipo", "fallas", "rotulo", "origen"}
    assert out["ramas"][0]["nombre"] == "Contacto 13-14 · Seguridad de parada de emergencia y tapa del tanque"
    assert out["ramas"][1]["nombre"] == "Cable"  # sin ese conductor: el genérico, nunca el id
    assert out["juntas"][0]["nombre"] == "J x"
    assert nombres_en_tabla(tabla, {}) is tabla


def test_un_cable_se_nombra_por_sus_extremos():
    n = Nombres(_doc(arranque_directo()))
    ramas = n.ramas()
    assert ramas["-W1.1"] == "Cable Contactor → Motor"
    assert any(v == "Cable Red de suministro → Interruptor general" for v in ramas.values())
