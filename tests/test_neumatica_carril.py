"""El circuito de aire en el carril del documento (plan V8.9 D1, D13; F1b).

- Un log VIEJO (V8.1–V8.8: tablero eléctrico + escena) regenera byte-idéntico: firmas, comandos,
  circuito, ERC y BOM contra la foto congelada ANTES de F1b (`data/carril_v81_golden.json`).
- `add_device` acepta refs neumáticas con designación de dos letras (-MM, -QM, -AZ) y `add_tubo`
  une sus puertos: estricto al entrar (clave desconocida con su corrección, un borne no es un
  puerto) y tolerante al regenerar (la clave vieja se ignora; un tubo roto se suprime en la carga).
- La bobina de la electroválvula es una carga del mando: la red eléctrica la ve.
- BOM por metro de tubo; `get_circuit` y `electrical_check` muestran el aire.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tablero_electrico import arranque_directo

from apolo.commands.electrico import prefijar
from apolo.commands.errors import CommandError
from apolo.doc.document import Document, DocumentError
from apolo.library.catalog import CATALOG
from apolo.library.electrico.colocacion_catalogo import ColocacionError, aparatos_desde_catalogo
from apolo.library.neumatica.bobinas import bornes_bobina, verificar
from apolo.services import electrico as S

GOLDEN = Path(__file__).parent / "data" / "carril_v81_golden.json"


def _viejo() -> Document:
    """El log de la foto congelada (lo mismo que armó el script que la generó, sobre 68b1222)."""
    d = Document("golden-carril")
    d.execute("set_variable", {"name": "L", "expression": "2.5"})
    d.execute("create_box", {"name": "Motor", "width": 100, "depth": 80, "height": 80,
                             "position": {"x": 0, "y": 0, "z": 40}})
    d.execute_many(arranque_directo())
    d.execute("add_wire", {"puntos": ["-Q1:2", "-Q2:1"], "tipo": "COND-H07VK-2.5", "color": "BK",
                           "largo_m": "=L"})
    return d


def _foto(d: Document) -> dict:
    crudo = {"firmas": list(d._regen_sigs), "comandos": d.commands, "circuito": S.circuito(d),
             "chequeo": S.chequeo(d), "bom": S.filas_bom(d)}
    return json.loads(json.dumps(crudo, ensure_ascii=False, sort_keys=True, default=str))


def test_un_log_viejo_regenera_byte_identico():
    esperado = json.loads(GOLDEN.read_text(encoding="utf-8"))
    d = _viejo()
    assert _foto(d) == esperado
    # y abierto desde su .apolo (carga tolerante), igual
    otra = Document.from_apolo_bytes(d.to_apolo_bytes(), tolerant=True)
    assert otra.regen_suppressed == [] and _foto(otra)["firmas"] == esperado["firmas"] and _foto(otra)["circuito"] == esperado["circuito"]


# ── el circuito de aire ──────────────────────────────────────────────────────────────────


def dev(ref: str, **p) -> dict:
    return {"type": "add_device", "params": {"ref": ref, **p}}


def tubo(desde: str, hasta: str, ref: str = "TUBO-PU-6", **p) -> dict:
    return {"type": "add_tubo", "params": {"desde": desde, "hasta": hasta, "ref": ref, **p}}


SERVICIO = {"carrera_mm": 200, "velocidad_m_s": 0.5, "masa_kg": 2}


def circuito_aire() -> list[dict]:
    return [
        dev("FR-G14", ajustes={"p_regulada_bar": 6}),
        dev("CORTE-ESC-G14"),
        dev("VAL-52-MONO-G18"),
        dev("CIL-ISO15552-32", servicio=SERVICIO),
        tubo("-AZ1:2", "-QM1:1", "TUBO-PU-8", largo_m=0.5),
        tubo("-QM1:2", "-QM2:1", "TUBO-PU-8", largo_m=1.0),
        tubo("-QM2:4", "-MM1:A", largo_m=1.5),
        tubo("-QM2:2", "-MM1:B"),
    ]


@pytest.fixture
def aire() -> Document:
    d = Document("aire")
    d.execute_many(circuito_aire())
    return d


def _params(d: Document, tipo: str) -> list[dict]:
    return [c["params"] for c in d.commands if c["type"] == tipo]


def test_designaciones_de_dos_letras_materializadas(aire):
    assert [p["designacion"] for p in _params(aire, "add_device")] == ["-AZ1", "-QM1", "-QM2", "-MM1"]
    # el aire numera aparte de lo eléctrico: un contactor sigue siendo -Q1
    aire.execute("add_device", {"ref": "CONT-9A-24VDC", "ubicacion": "+TAB1"})
    assert _params(aire, "add_device")[-1]["designacion"] == "-Q1"
    m = aire.electrico
    cil = next(x for x in m.dispositivos if x.designacion == "-MM1")
    assert cil.funcion == "MM" and cil.bornes == () and [p.id for p in cil.puertos] == ["A", "B"]
    assert cil.servicio == {"carrera_mm": 200.0, "velocidad_m_s": 0.5, "masa_kg": 2.0}
    assert len(m.tubos) == 4 and m.tubos[2].desde == "-QM2:4" and m.tubos[2].largo_m == 1.5


def test_el_carril_de_aire_no_toca_la_escena_ni_sus_firmas():
    d = Document("x")
    d.execute("create_box", {"name": "Bastidor", "width": 100, "depth": 100, "height": 10})
    antes = list(d._regen_sigs)
    d.execute_many(circuito_aire())
    assert d._regen_sigs == antes and len(d.scene) == 1


def test_add_tubo_es_estricto_al_entrar(aire):
    with pytest.raises(CommandError, match=r"largo.*¿quisiste decir.*largo_m"):
        aire.execute("add_tubo", {"desde": "-QM2:4", "hasta": "-MM1:A", "ref": "TUBO-PU-6", "largo": 1})
    with pytest.raises(DocumentError, match=r"A1 es un BORNE eléctrico de -QM2.*add_wire"):
        aire.execute("add_tubo", {"desde": "-QM2:A1", "hasta": "-MM1:A", "ref": "TUBO-PU-6"})
    with pytest.raises(DocumentError, match=r"no tiene el puerto C; puertos: A, B"):
        aire.execute("add_tubo", {"desde": "-QM2:4", "hasta": "-MM1:C", "ref": "TUBO-PU-6"})
    with pytest.raises(DocumentError, match=r"no es un tubo de aire"):
        aire.execute("add_tubo", {"desde": "-QM2:4", "hasta": "-MM1:A", "ref": "COND-H07VK-2.5"})
    with pytest.raises(CommandError, match=r"le falta el puerto"):
        aire.execute("add_tubo", {"desde": "-QM2", "hasta": "-MM1:A", "ref": "TUBO-PU-6"})
    # un conductor a un puerto de aire también se nombra por su medio
    with pytest.raises(DocumentError, match=r"4 es un PUERTO de aire de -QM2.*add_tubo"):
        aire.execute("add_wire", {"puntos": ["-QM2:4", "-QM2:A1"]})
    assert len(aire.electrico.tubos) == 4  # nada de lo rechazado entró


def test_add_tubo_es_tolerante_al_regenerar(aire):
    tubos = [c for c in aire.commands if c["type"] == "add_tubo"]
    tubos[0]["params"]["color_viejo"] = "azul"  # una clave de un log viejo: el replay la ignora
    aire.regenerate()
    assert len(aire.electrico.tubos) == 4
    # en la carga, un tubo que nombra un puerto que no existe se SUPRIME (el log no se toca)
    tubos[1]["params"]["hasta"] = "-QM7:1"
    datos = aire.to_apolo_bytes()
    with pytest.raises(DocumentError, match=r"-QM7 no existe. ¿Quisiste decir: -QM1, -QM2\?"):
        Document.from_apolo_bytes(datos)  # estricto: dice qué falla y cómo corregirlo
    otra = Document.from_apolo_bytes(datos, tolerant=True)
    assert len(otra.electrico.tubos) == 3
    assert [s["command_id"] for s in otra.regen_suppressed] == [tubos[1]["id"]]
    assert next(c for c in otra.commands if c["id"] == tubos[1]["id"])["params"]["hasta"] == "-QM7:1"


def test_ajustes_y_servicio_contra_la_ficha():
    d = Document()
    with pytest.raises(DocumentError, match=r"p_regulada_bar de FR-G14 va entre 0.5 y 8.5"):
        d.execute("add_device", {"ref": "FR-G14", "ajustes": {"p_regulada_bar": 12}})
    with pytest.raises(DocumentError, match=r"no tiene el ajuste «Ir_A»; ajustes: p_regulada_bar"):
        d.execute("add_device", {"ref": "FR-G14", "ajustes": {"Ir_A": 3}})
    with pytest.raises(DocumentError, match=r"`servicio` sólo va en un cilindro; VAL-52-MONO-G18 es valvula"):
        d.execute("add_device", {"ref": "VAL-52-MONO-G18", "servicio": {"carrera_mm": 100}})
    with pytest.raises(DocumentError, match=r"la carrera de CIL-ISO6432-16 va entre 10 y 320 mm"):
        d.execute("add_device", {"ref": "CIL-ISO6432-16", "servicio": {"carrera_mm": 500}})
    with pytest.raises(DocumentError, match=r"es un tubo de aire: decláralo con add_tubo"):
        d.execute("add_device", {"ref": "TUBO-PU-6"})
    with pytest.raises(CommandError, match=r"carrera.*¿quisiste decir.*carrera_mm"):
        d.execute("add_device", {"ref": "CIL-ISO15552-32", "servicio": {"carrera": 100}})


def test_la_carrera_acepta_expresiones():
    d = Document()
    d.execute("set_variable", {"name": "S", "expression": "250"})
    d.execute("add_device", {"ref": "CIL-ISO15552-32", "servicio": {"carrera_mm": "=S"}})
    assert d.electrico.dispositivos[0].servicio["carrera_mm"] == 250.0


# ── la bobina en la red eléctrica ────────────────────────────────────────────────────────


def test_la_bobina_de_la_valvula_es_una_carga_del_mando(aire):
    def tension_cruzada(d):
        return [r for r in S.chequeo(d)["reglas"] if r["regla"] == "tensión cruzada" and r["estado"] != "ok"]

    suelta = [r for r in S.chequeo(aire)["reglas"] if r["regla"] == "borne suelto" and r["estado"] != "ok"]
    assert suelta and "-QM2:A1" in suelta[0]["elementos"]
    aire.execute_many([
        {"type": "add_device", "params": {"ref": "FUENTE-24VDC-2.5A", "designacion": "-T1", "ubicacion": "+TAB1"}},
        {"type": "add_wire", "params": {"puntos": ["-T1:L+", "-QM2:A1"], "color": "BU", "seccion_mm2": 0.75}},
        {"type": "add_wire", "params": {"puntos": ["-QM2:A2", "-T1:M"], "color": "BU", "seccion_mm2": 0.75}},
    ])
    assert not tension_cruzada(aire)
    valv = next(x for x in aire.electrico.dispositivos if x.designacion == "-QM2")
    assert [(c.bornes, str(c.tension), c.tipo) for c in valv.cargas] == [(("A1", "A2"), "24 VDC", "bobina")]


def test_las_bobinas_del_catalogo_siguen_la_convencion():
    assert bornes_bobina(["14"]) == {"14": ("A1", "A2")}
    assert bornes_bobina(["14", "12"]) == {"14": ("14A1", "14A2"), "12": ("12A1", "12A2")}
    for ref, c in CATALOG.items():
        if c.neumatico is not None and c.neumatico.modelo.get("bobinas"):
            pares = bornes_bobina(c.neumatico.modelo["bobinas"]).values()
            assert sorted(tuple(x.bornes) for x in c.electrico.cargas) == sorted(pares), ref
            assert c.electrico.montaje == "campo", ref  # D6: nunca dentro del tablero


def test_el_loader_rechaza_una_bobina_que_no_calza():
    neu = CATALOG["VAL-52-BI-G18"].neumatico
    mono = CATALOG["VAL-52-MONO-G18"].electrico  # A1/A2: falta la bobina 12
    with pytest.raises(ValueError, match=r"falta la carga `bobina` de la bobina 14 entre los bornes 14A1–14A2"):
        verificar(neu, mono, "X", str)
    with pytest.raises(ValueError, match=r"lleva su bloque `electrico:`"):
        verificar(neu, None, "X", str)


def test_el_tablero_no_admite_valvulas():
    with pytest.raises(ColocacionError, match=r"-QM1 \(VAL-52-MONO-G18\) es neumático.*panel neumático"):
        aparatos_desde_catalogo([{"designacion": "-QM1", "ref": "VAL-52-MONO-G18"}], CATALOG)


def test_insert_project_prefija_los_puertos_del_tubo():
    p = prefijar("add_tubo", {"desde": "-QM2:4", "hasta": "-MM1:A", "ref": "TUBO-PU-6"}, "Faja1", "c9")
    assert (p["desde"], p["hasta"]) == ("=Faja1-QM2:4", "=Faja1-MM1:A")


# ── lo que ven los clientes: circuito, chequeo y BOM ─────────────────────────────────────


def test_get_circuit_muestra_el_aire(aire):
    c = S.circuito(aire)
    cil = next(x for x in c["dispositivos"] if x["designacion"] == "-MM1")
    assert cil["bornes"] == [] and [p["id"] for p in cil["puertos"]] == ["A", "B"]
    assert cil["servicio"]["carrera_mm"] == 200
    neu = c["neumatica"]
    assert neu["resumen"]["n_tubos"] == 4 and c["resumen"]["n_tubos"] == 4
    linea = next(x for x in neu["lineas"] if "-MM1:A" in x["puertos"])
    assert linea["puertos"] == ["-QM2:4", "-MM1:A"] and linea["presion_bar"] == 6.0
    escape = next(p for p in next(x for x in c["dispositivos"] if x["designacion"] == "-QM2")["puertos"]
                  if p["id"] == "3")
    assert escape["conectado"] is False
    # filtrado por un aparato: sólo sus líneas y tubos
    solo = S.circuito(aire, "-MM1")["neumatica"]
    assert {t["hasta"] for t in solo["tubos"]} == {"-MM1:A", "-MM1:B"}


def test_electrical_check_muestra_el_aire(aire):
    ch = S.chequeo(aire)
    del_aire = [r for r in ch["reglas"] if r.get("medio") == "aire"]
    assert ch["n_tubos"] == 4 and len(del_aire) == 9  # + la relación de carga (F4)
    assert all(r["estado"] == "ok" for r in del_aire), [r["detalle"] for r in del_aire if r["estado"] != "ok"]


def test_sin_corte_con_escape_la_puerta_lo_ve_rojo():
    d = Document()
    d.execute_many([dev("FR-G14", ajustes={"p_regulada_bar": 6}), dev("VAL-52-MONO-G18"),
                    dev("CIL-ISO15552-32", servicio=SERVICIO),
                    tubo("-AZ1:2", "-QM1:1"), tubo("-QM1:4", "-MM1:A"), tubo("-QM1:2", "-MM1:B")])
    rojas = [r for r in S.reglas_erc(d) if r["estado"] == "error" and r["regla"] == "aislamiento del aire"]
    assert rojas and "ISO 4414" in rojas[0]["norma"]


def test_la_bom_compra_el_tubo_por_metro(aire):
    filas = {(f["ref"], f.get("longitud_mm")): f for f in S.filas_bom(aire)}
    assert filas[("TUBO-PU-8", 1500.0)]["cantidad"] == 1  # 0,5 + 1,0 m declarados
    assert filas[("TUBO-PU-6", 1500.0)]["cantidad"] == 1
    sin = filas[("TUBO-PU-6", None)]
    assert sin["sin_largo"] is True and "sin largo declarado" in sin["aviso"]
    assert {r for r, _ in filas} >= {"FR-G14", "CORTE-ESC-G14", "VAL-52-MONO-G18", "CIL-ISO15552-32"}
