"""El ítem `interfaz.nombres_por_funcion` y la regla «nombres por función» de `delivery_check`
(plan nombres-por-funcion F2: D4, D5, D8, A7–A9, A12, A15, A17): el criterio sobre los 45 rótulos
de la F0, la unicidad por (aspecto, clase), los estados del selector, lo que el tipo ya nombra, y
los estados del ítem (NO_APLICA, SIN_EVALUAR, FALLA, OK)."""

from __future__ import annotations

import pytest
from tablero_electrico import arranque_directo, con_rotulos

from apolo.doc import Document
from apolo.library.calidad import nombres as nb
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.library.calidad.puerta import semaforo_entrega
from apolo.library.calidad.registro import REGISTRO, evaluar
from apolo.library.catalog import CATALOG
from apolo.services import escenarios as E
from apolo.services.nombres_aparatos import insumo_puerta

# (rótulo, ref, ¿debería valer?, ¿vale con el criterio?) — la tabla de la F0 § 3, fila por fila.
# Los dos falsos ✗ («Paro de emergencia», «Marcha/paro») son el mismo caso: la función de esos
# aparatos ES su nombre de catálogo. Se aceptan (A7): la seta única sale del ítem por A8 y, con dos,
# hay que decir CUÁL igual («Paro de emergencia nivel 0»). La tabla de tipos no se abre.
F0 = [
    ("Interruptor general", "SECC-25A-3P", True, True),
    ("Seccionador rotativo", "SECC-25A-3P", False, False),
    ("Marcha", "PULS-22-VERDE-NA", True, True),
    ("Paro", "PULS-22-ROJO-NC", True, True),
    ("Rearme de seguridad", "PULS-22-AZUL-NA", True, True),
    ("Rearme", "PULS-22-AZUL-NA", True, True),
    ("Tapa del tanque", "RESG-2NC", True, True),
    ("Pulsador verde", "PULS-22-VERDE-NA", False, False),
    ("-S1", "PULS-22-VERDE-NA", False, False),
    ("Resguardo", "RESG-2NC", False, False),
    ("RESG-2NC", "RESG-2NC", False, False),
    ("RESG-2NC", "PULS-22-VERDE-NA", False, False),
    ("rs_ok", "RESG-2NC", False, False),
    ("Selector 2 pos.", "SEL-22-2POS-1NA", False, False),
    ("Pulsador Ø22 verde 1NA", "PULS-22-VERDE-NA", False, False),
    ("Selector 2 posiciones", "SEL-22-2POS-1NA", False, False),
    ("Modo", "SEL-22-2POS-1NA", True, True),
    ("Parada de emergencia", "ESTOP-40-2NC", True, True),
    ("Paro de emergencia", "ESTOP-40-2NC", True, False),  # falso ✗ (anotado en la F0)
    ("Seta de emergencia", "ESTOP-40-2NC", False, False),
    ("Interruptor de tapa", "RESG-2NC", True, True),
    ("Interruptor de seguridad", "RESG-2NC", False, False),
    ("Recipiente bajo la descarga", "RESG-2NC", True, True),
    ("Piloto ámbar", "PILOTO-24V-AMBAR", False, False),
    ("Tapa abierta", "PILOTO-24V-AMBAR", True, True),
    ("Falla", "PILOTO-24V-ROJO", True, True),
    ("Piloto LED", "PILOTO-24V-VERDE", False, False),
    ("Luz verde", "PILOTO-24V-VERDE", False, False),
    ("Encendido", "PILOTO-24V-VERDE", False, False),
    ("Compuerta cerrada", "SENS-MAG-RANURA-PNP", True, True),
    ("Detector magnético", "SENS-MAG-RANURA-PNP", False, False),
    ("Fotocélula", "SENS-IND-M18-PNP", False, False),
    ("Sensor de nivel bajo", "SENS-IND-M18-PNP", True, True),
    ("c160 · Cable", "PULS-22-VERDE-NA", False, False),
    ("%IX0.1", "PULS-22-VERDE-NA", False, False),
    ("Marcha -S1", "PULS-22-VERDE-NA", False, False),
    ("Botonera nivel 0", "BOTONERA-2", True, True),
    ("Marcha/paro", "BOTONERA-2", True, False),  # falso ✗ (anotado en la F0)
    ("Válvula de la compuerta", "VAL-52-MONO-G18", True, True),
    ("Electroválvula 5/2", "VAL-52-MONO-G18", False, False),
    ("Final de carrera", "RESG-2NC", False, False),
    ("Sobrecarrera superior", "RESG-2NC", True, True),
    ("Cadena floja 1", "RESG-2NC", True, True),
    ("Panel de operador", "HMI-7IN-24VDC", False, False),
    ("Puerta nivel 0", "RESG-2NC", True, True),
]


def test_la_tabla_de_la_f0_tiene_sus_45_rotulos_y_ningun_falso_valido():
    assert len(F0) == 45
    assert [r for r, _ref, debe, vale in F0 if vale and not debe] == []
    assert [r for r, _ref, debe, vale in F0 if debe and not vale] == ["Paro de emergencia",
                                                                       "Marcha/paro"]


@pytest.mark.parametrize("rotulo,ref,debe,vale", F0, ids=[f"{i}-{r}" for i, (r, *_x) in enumerate(F0, 1)])
def test_criterio_sobre_los_rotulos_de_la_f0(rotulo, ref, debe, vale):
    motivo = nb.motivo_rotulo(rotulo, ref, CATALOG[ref].name)
    assert (motivo is None) is vale, motivo


def _ap(des, tipo, rotulo="", **kw) -> dict:
    return {"designacion": des, "tipo": tipo, "rotulo": rotulo, "ref": kw.pop("ref", ""),
            "nombre_ficha": kw.pop("nombre_ficha", ""), "estados": kw.pop("estados", {}),
            "claves": kw.pop("claves", []), "piezas": kw.pop("piezas", [f"p{des}"]), **kw}


def _item(nombres, hechos=None) -> dict:
    ins = {"nombres": nombres,
           "hechos": hechos if hechos is not None else {"elementos": {"operables": nb.elementos(nombres)}}}
    (it,) = evaluar(ins, registro=(nb.ENTRADA,))["items"]
    return it


# ------------------------------------------------------------------ unicidad (A9 y el aspecto)
def test_la_unicidad_va_por_aspecto_y_clase():
    marcha = [_ap("-S1", "pulsador", "Marcha"), _ap("-P1", "piloto", "Marcha")]
    assert nb.casos(marcha) == []  # el botón y su piloto llevan la misma leyenda (A9)
    dos = [_ap("-S1", "pulsador", "Marcha"), _ap("-S5", "pulsador", "marcha")]
    assert [c["motivo"] for c in nb.casos(dos)] == ["repetido con -S5", "repetido con -S1"]
    fajas = [_ap("=Faja1-S1", "pulsador", "Marcha"), _ap("=Faja2-S1", "pulsador", "Marcha")]
    assert nb.casos(fajas) == []
    assert nb.aspecto("=Faja1-S1") == "=Faja1" and nb.aspecto("-S1") == ""


def test_dos_insert_project_con_marcha_pasan():
    origen = Document("faja con tablero")  # insert_project pide sólidos: el motor
    motor = origen.execute("insert_component", {"component": "MOTOR-075", "name": "Motorreductor"})
    origen.execute_many(con_rotulos(arranque_directo(pieza_motor=next(
        f for f, x in origen.scene.items() if x.command_id == motor))))
    lay = Document("layout")
    digest = lay.add_attachment(origen.to_apolo_bytes())
    lay.execute("insert_project", {"attachment": digest, "name": "Faja 1"})
    lay.execute("insert_project", {"attachment": digest, "name": "Faja2", "position": {"x": 3000}})
    ins = insumo_puerta(lay)
    alcance = {a["designacion"] for a in nb.en_alcance(ins["aparatos"])}
    assert alcance == {f"={f}-{d}" for f in ("Faja1", "Faja2") for d in ("S1", "S2", "P1")}
    assert nb.casos(ins["aparatos"]) == []
    assert _item(ins)["estado"] == OK


# ------------------------------------------------------------------ estados (D5 regla 5)
def test_el_selector_sin_estados_falla_y_con_ellos_pasa():
    sel = _ap("-S4", "selector", "Modo", claves=["0", "I"])
    (c,) = nb.casos([sel])
    assert "le falta el nombre de la posición «0»" in c["motivo"]
    assert "le falta el nombre de la posición «I»" in c["motivo"]
    crudos = {**sel, "estados": {"0": "0", "I": "Ciclo"}}
    assert "«0»" in nb.casos([crudos])[0]["motivo"]
    assert nb.casos([{**sel, "estados": {"0": "Manual", "I": "Ciclo"}}]) == []
    valv = _ap("-QM1", "electrovalvula", "Compuerta", manual=True, claves=["14", "12"],
               estados={"14": "Abre la compuerta"})
    assert "«12»" in nb.casos([valv])[0]["motivo"]
    # sin mando manual la electroválvula no es un operable
    assert nb.en_alcance([{**valv, "manual": False}]) == []


# ------------------------------------------------------------------ A8: el tipo que ya es la función
def test_lo_que_el_tipo_ya_nombra_queda_fuera_si_es_unico():
    unicos = [_ap("-S0", "seta"), _ap("-Q1", "seccionador"), _ap("-A1", "hmi"),
              _ap("-QM0", "valvula_corte")]
    assert nb.en_alcance(unicos) == []
    assert nb.elementos({"aparatos": unicos}) == {}
    dos = [_ap("-S0", "seta"), _ap("-S9", "seta", "Paro de emergencia",
                                    nombre_ficha="Paro de emergencia Ø40")]
    cs = nb.casos(dos)
    assert [c["designacion"] for c in cs] == ["-S0", "-S9"]  # con dos, hay que decir CUÁL
    assert cs[1]["motivo"].startswith("genérico")
    # cada aspecto con su seta única: fuera
    assert nb.en_alcance([_ap("=Faja1-S0", "seta"), _ap("=Faja2-S0", "seta")]) == []


# ------------------------------------------------------------------ los estados del ítem
def test_no_aplica_sin_carril():
    doc = Document("sin tablero")
    doc.execute("create_box", {"name": "Caja", "width": 10, "depth": 10, "height": 10})
    assert insumo_puerta(doc) is None
    it = _item(None)
    assert it["estado"] == NO_APLICA and "sin mandos" in it["detalle"]


def test_sin_evaluar_si_el_control_revienta():
    assert _item({"error": "KeyError: -K9"})["estado"] == SIN_EVALUAR
    roto = {"aparatos": [{"tipo": "pulsador"}]}  # sin designación: el control lanza
    it = _item(roto, hechos={"elementos": {"operables": {"pulsador": 1}}})
    assert it["estado"] == SIN_EVALUAR and "el control falló" in it["detalle"]


def test_lo_derivado_no_aprueba_y_va_como_sugerencia():
    ap = [_ap("-B1", "resguardo", sugerencia="Interruptor de tapa", piezas=["c66"])]
    it = _item({"aparatos": ap})
    assert it["estado"] == FALLA and it["piezas"] == ["c66"]
    (caso,) = it["evidencia"]["casos"]
    assert caso == {"designacion": "-B1", "tipo": "resguardo", "motivo": "sin rótulo",
                    "piezas": ["c66"], "sugerencia": "Interruptor de tapa"}
    ok = _item({"aparatos": [{**ap[0], "rotulo": "Tapa del tanque"}]})
    assert ok["estado"] == OK and ok["evidencia"]["evaluados"] == 1


def test_el_item_esta_en_el_registro_con_su_norma():
    (e,) = [x for x in REGISTRO if getattr(x, "id", "") == "interfaz.nombres_por_funcion"]
    assert e is nb.ENTRADA and e.familia == "seguridad" and e.elementos == "operables"
    assert e.norma == "IEC 60204-1:2016 §16.3 (mandos) · criterio de diseño (pilotos y sensores)"


# ------------------------------------------------------------------ la entrega (D8, D2, A12, A17)
def test_la_entrega_avisa_lo_repetido_y_el_resguardo_sin_estados_y_la_puerta_no_lo_repite():
    ap = [_ap("-S1", "pulsador", "Marcha"), _ap("-K2", "rele_seguridad"),
          _ap("-K3", "rele_seguridad", "Seguridad del recipiente"),
          _ap("-B4", "resguardo", "Recipiente acoplado"), _ap("-F1", "itm"), _ap("-F2", "itm")]
    filas = nb.regla_entrega({"aparatos": ap})
    assert [f["regla"] for f in filas] == ["nombres por función · aparatos repetidos",
                                           "nombres por función · resguardo sin estados"]
    assert "-K2 (sin rótulo)" in filas[0]["detalle"] and "-K3" not in filas[0]["detalle"]
    assert "-F1" not in filas[0]["detalle"]  # las protecciones se nombran por lo que protegen
    assert nb.regla_entrega(None) is None
    con = [{**a, "estados": {"cerrado": "Acoplado", "abierto": "Sin recipiente"}}
           if a["tipo"] == "resguardo" else a for a in ap if a["designacion"] != "-K2"]
    assert nb.regla_entrega({"aparatos": con}) == []
    entrega = {"veredicto": "AMARILLO", "bloqueantes": [],
               "avisos": [{"regla": f["regla"], "piezas": [], "detalle": f["detalle"]} for f in filas]}
    r = semaforo_entrega({"entrega": entrega})
    assert r["estado"] == OK and len(r["evidencia"]["con_item_propio"]) == 2
    otro = {**entrega, "avisos": entrega["avisos"] + [{"regla": "lint", "piezas": [], "detalle": "x"}]}
    assert semaforo_entrega({"entrega": otro})["estado"] == FALLA


def test_la_entrega_del_tablero_avisa_los_mandos_sin_rotulo():
    from apolo.library.delivery import delivery_report

    doc = Document("tablero")
    doc.execute_many(arranque_directo())
    ins = insumo_puerta(doc)
    rep = delivery_report(n_solidos=0, interferencias=[], soundness={"has_ground": True}, lints=[],
                          integridad=[], suprimidos=[], poses=None, nombres=ins)
    (aviso,) = [a for a in rep["avisos"] if a["regla"].startswith(nb.REGLA_ENTREGA)]
    assert "-S1 (sin rótulo), -S2 (sin rótulo), -P1 (sin rótulo)" in aviso["detalle"]
    assert "-S0" not in aviso["detalle"] and "-Q1" not in aviso["detalle"]  # A8


# ------------------------------------------------------------------ set_scenario (D14)
def test_set_scenario_avisa_ids_en_la_descripcion():
    doc = Document("x")
    fid = doc.execute("create_box", {"name": "Vástago", "width": 10, "depth": 10, "height": 10})
    assert E.avisos_descripcion(doc, {"descripcion": "Arranca con la compuerta cerrada"}) == []
    (a,) = E.avisos_descripcion(doc, {"descripcion": f"(c68_vastago inicial 200 mm) y {fid}"})
    assert "«c68_vastago»" in a and f"«{fid}»" in a
    assert E.avisos_descripcion(doc, {"descripcion": "-B4 abierto, Q0.2 pegada"}) == []
