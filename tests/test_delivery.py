"""V6.9 · Puerta de ENTREGA: agregador puro (`library/delivery.py`) + endpoint
`POST /api/delivery-check` + alarma ambiental `aviso_estructura`.

El caso de regresión es el camastro-v2 (proyecto 71): 85 piezas entregadas con
cremalleras FLOTANDO y 0 anclajes declarados — el agente validó lo que el prompt
pedía por su letra y se saltó la sujeción. La puerta lo habría puesto en ROJO."""

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.delivery import (
    AMARILLO, AVISO_SIN_ANCLAJES, MIN_SOLIDOS_SUJECION, ROJO, VERDE, delivery_report,
)


# ------------------------------------------------------- agregador puro
def _reporte(**kw):
    base = dict(
        n_solidos=10,
        interferencias=[],
        soundness={"has_ground": True, "floating": [], "isolated": []},
        lints=[],
        integridad=[],
        suprimidos=[],
        poses=None,
        gravedad=None,
    )
    base.update(kw)
    return delivery_report(**base)


def test_sano_es_verde_y_declara_lo_que_no_aplica():
    rep = _reporte()
    assert rep["veredicto"] == VERDE
    assert rep["bloqueantes"] == [] and rep["avisos"] == []
    assert "sujeción declarada" in rep["resumen"]["chequeos_ok"]
    # lo no corrido se DECLARA, jamás cuenta como verde
    assert any("poses" in x for x in rep["no_aplica"])
    assert any("gravedad" in x for x in rep["no_aplica"])


def test_sin_anclajes_es_rojo_desde_el_umbral():
    rep = _reporte(soundness={"has_ground": False, "floating": [], "isolated": []})
    assert rep["veredicto"] == ROJO
    assert any(b["regla"] == "sujeción · sin anclajes" for b in rep["bloqueantes"])
    # bajo el umbral (croquis de 2-3 piezas) no se exige — pero se declara, no se calla
    chico = _reporte(n_solidos=MIN_SOLIDOS_SUJECION - 1,
                     soundness={"has_ground": False, "floating": [], "isolated": []})
    assert chico["veredicto"] == VERDE
    assert any("sujeción" in x for x in chico["no_aplica"])


def test_flotantes_es_rojo_con_nombres():
    """El defecto real del 71: grounds declarados pero piezas SIN camino de carga."""
    nombres = {"c9": "Cremallera izquierda", "c10": "Cremallera derecha"}
    rep = _reporte(
        soundness={"has_ground": True, "floating": ["c9", "c10"], "isolated": ["c10"]},
        nombre_de=lambda fid: nombres.get(fid, fid),
    )
    assert rep["veredicto"] == ROJO
    b = next(b for b in rep["bloqueantes"] if b["regla"] == "sujeción · piezas flotantes")
    assert "Cremallera izquierda (c9)" in b["piezas"]
    assert "1 sin ninguna unión" in b["detalle"]


def test_tornilleria_flotante_avisa_sin_bloquear():
    """Convención de la casa (lints V7.2b): la tornillería no es nodo estructural — la
    representa su fasten. Suelta en el grafo declarado → AVISO, no ROJO (el caso real:
    los 8 pernos/tuercas de chumacera del 38, añadidos por cirugía sin fasten propio)."""
    rep = _reporte(tornilleria_flotante=["c1130", "c1131"])
    assert rep["veredicto"] == AMARILLO
    a = next(a for a in rep["avisos"] if a["regla"] == "sujeción · tornillería sin unión declarada")
    assert "c1130" in " ".join(a["piezas"]) and "fasten" in a["detalle"]


def test_interferencias_y_lints():
    rep = _reporte(interferencias=[{"a": "c1", "nombre_a": "Pata", "b": "c2",
                                    "nombre_b": "Larguero", "volumen_mm3": 320.0}])
    assert rep["veredicto"] == ROJO
    assert any("Pata ↔ Larguero" in b["detalle"] for b in rep["bloqueantes"])
    # truncado (MAX_PAIRS) → aviso, sin caps silenciosos
    rep2 = _reporte(interferencias_truncado=True)
    assert rep2["veredicto"] == AMARILLO
    assert any("truncado" in a["regla"] for a in rep2["avisos"])
    # lints solos → AMARILLO con la recomendación pegada
    rep3 = _reporte(lints=[{"regla": "pre-entrega · barreno sin perno", "estado": "aviso",
                            "detalle": "2 barrenos", "recomendacion": "usa join_bolted"}])
    assert rep3["veredicto"] == AMARILLO
    assert any("join_bolted" in a["detalle"] for a in rep3["avisos"])


def test_salud_del_documento():
    assert _reporte(integridad=["feature huérfana c3"])["veredicto"] == ROJO
    assert _reporte(suprimidos=[{"command_id": "c7", "type": "fillet"}])["veredicto"] == ROJO
    rep = _reporte(integridad=["degradado: instancing perdido"])
    assert rep["veredicto"] == AMARILLO  # degradado NO bloquea, pero se avisa
    assert "salud del documento" in rep["resumen"]["chequeos_ok"]


def test_poses_declaradas():
    mala = {"estudio": "reclinar", "t": 1.0, "joint_values": {"pivote": -50},
            "colisiones": [{"a": "c1", "b": "c2", "volumen_mm3": 5.0}]}
    rep = _reporte(poses=[mala])
    assert rep["veredicto"] == ROJO
    b = next(b for b in rep["bloqueantes"] if b["regla"] == "colisión en pose declarada")
    assert "reclinar" in b["detalle"] and "pivote" in b["detalle"]
    # pose no evaluable = AMARILLO declarando que quedó SIN verificar (nunca verde)
    rep2 = _reporte(poses=[{"estudio": "viejo", "error": "fotograma sin 'values'"}])
    assert rep2["veredicto"] == AMARILLO
    assert any("SIN verificar" in a["detalle"] for a in rep2["avisos"])
    # todas limpias → cuenta ok con su conteo
    rep3 = _reporte(poses=[{**mala, "colisiones": []}])
    assert rep3["veredicto"] == VERDE
    assert "poses declaradas (1)" in rep3["resumen"]["chequeos_ok"]


def test_gravedad_opt_in():
    rep = _reporte(gravedad={"fell": [{"id": "c5", "nombre": "Guarda", "caida_mm": 812.0}],
                             "estables": [], "settled": True})
    assert rep["veredicto"] == ROJO
    assert any("Guarda" in b["detalle"] for b in rep["bloqueantes"])
    ok = _reporte(gravedad={"fell": [], "estables": [{"id": "c1"}], "settled": True})
    assert "gravedad" in ok["resumen"]["chequeos_ok"]


# ------------------------------------------------------- endpoint + alarma
@pytest.fixture()
def client():
    api.DOC = Document("delivery-test")
    return TestClient(api.app)


def _caja(client, i, x):
    r = client.post("/api/commands", json={"type": "create_box", "params": {
        "name": f"Caja {i}", "width": 100, "depth": 100, "height": 100,
        "position": {"x": x}}})
    assert r.status_code == 200
    return r


def test_endpoint_rojo_a_verde(client):
    """El flujo completo del 71 en miniatura: 5 piezas sin declarar → ROJO; declarada
    la estructura (ground + cadena de fasten) → VERDE."""
    for i in range(5):
        r = _caja(client, i, i * 200)
    fids = [f["id"] for f in r.json()["features"]]

    rep = client.post("/api/delivery-check", json={}).json()
    assert rep["veredicto"] == ROJO
    assert any(b["regla"] == "sujeción · sin anclajes" for b in rep["bloqueantes"])

    acciones = [{"type": "ground", "params": {"name": "g0", "feature": fids[0]}}]
    acciones += [{"type": "fasten", "params": {"name": f"f{i}", "a": fids[i],
                                               "b": fids[i + 1], "kind": "perno"}}
                 for i in range(4)]
    assert client.post("/api/commands/batch", json={"actions": acciones}).status_code == 200

    rep = client.post("/api/delivery-check", json={}).json()
    assert rep["veredicto"] == VERDE, rep
    assert "sujeción declarada" in rep["resumen"]["chequeos_ok"]
    assert "interferencias" in rep["resumen"]["chequeos_ok"]


def _mecanismo():
    """base + brazo (junta prismática X) + obstáculo en x=300 (espejo de test_verify):
    en diseño el brazo (x −50..50) no toca el obstáculo (x 270..330); a desliza=300 lo
    invade de lleno; a 220.01 apenas lo roza (36 mm³ ≤ tolerancia de asiento)."""
    doc = api.DOC
    base = doc.execute("create_box", {"name": "base", "width": 100, "depth": 100, "height": 100})
    arm = doc.execute("create_box", {"name": "brazo", "width": 100, "depth": 60, "height": 200})
    doc.execute("create_box", {"name": "obst", "width": 60, "depth": 60, "height": 60,
                               "position": {"x": 300}})
    doc.execute("add_joint", {"name": "desliza", "type": "prismatica", "parent": base,
                              "child": arm, "axis": {"x": 1}, "lower": 0, "upper": 400})


def test_endpoint_pose_declarada_colisiona(client):
    """Estudio de movimiento cuyo recorrido invade un obstáculo: la puerta evalúa las
    poses DECLARADAS (camino V6.8-C) y pone el proyecto en ROJO nombrando el estudio."""
    _mecanismo()
    r = client.put("/api/motion", json={"name": "barrido", "keyframes": [
        {"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 300}}]})
    assert r.status_code == 200

    rep = client.post("/api/delivery-check", json={}).json()
    assert rep["veredicto"] == ROJO
    b = next(b for b in rep["bloqueantes"] if b["regla"] == "colisión en pose declarada")
    assert "barrido" in b["detalle"] and "desliza" in b["detalle"]
    # el mismo estudio acotado a una pose segura → la regla de poses pasa
    client.put("/api/motion", json={"name": "barrido", "keyframes": [
        {"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 100}}]})
    rep = client.post("/api/delivery-check", json={}).json()
    assert not any(b["regla"] == "colisión en pose declarada" for b in rep["bloqueantes"])
    assert "poses declaradas (1)" in rep["resumen"]["chequeos_ok"]


def test_endpoint_poses_solo_reposo_y_asiento_tolerado(client):
    """El caso real del camastro 70: los fotogramas de TRÁNSITO (la barra saltando
    dientes) no son poses de entrega — solo se evalúan los de REPOSO (extremos +
    dwells); y el contacto de ASIENTO (la barra en su muesca, ~2 mm³) se tolera y se
    DECLARA en vez de bloquear."""
    _mecanismo()
    # el 300 (colisión franca) va en MEDIO sin sostener → tránsito → no bloquea
    client.put("/api/motion", json={"name": "m", "keyframes": [
        {"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 300}},
        {"t": 2, "values": {"desliza": 100}}]})
    rep = client.post("/api/delivery-check", json={}).json()
    assert not any(b["regla"] == "colisión en pose declarada" for b in rep["bloqueantes"])
    # el MISMO 300 SOSTENIDO (dwell) = pose de reposo → ROJO
    client.put("/api/motion", json={"name": "m", "keyframes": [
        {"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 300}},
        {"t": 1.5, "values": {"desliza": 300}}, {"t": 2, "values": {"desliza": 100}}]})
    rep = client.post("/api/delivery-check", json={}).json()
    assert any(b["regla"] == "colisión en pose declarada" for b in rep["bloqueantes"])
    # roce de asiento (36 mm³ ≤ 50) en el extremo → tolerado y DECLARADO, no bloquea
    client.put("/api/motion", json={"name": "m", "keyframes": [
        {"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 220.01}}]})
    rep = client.post("/api/delivery-check", json={}).json()
    assert rep["veredicto"] != ROJO
    assert any("contactos de asiento tolerados: 1" in x
               for x in rep["resumen"]["chequeos_ok"]), rep["resumen"]


def test_alarma_ambiental_en_mutaciones(client):
    """V6.9-B: desde el 5.º sólido sin grounds, CADA retorno de mutación trae
    `aviso_estructura`; declarar el primer ground la apaga; las lecturas no la llevan."""
    for i in range(4):
        r = _caja(client, i, i * 200)
    assert "aviso_estructura" not in r.json()  # bajo el umbral: silencio
    r = _caja(client, 4, 800)
    assert r.json()["aviso_estructura"] == AVISO_SIN_ANCLAJES
    # las LECTURAS no la llevan (no ensuciar consultas)
    assert "aviso_estructura" not in client.get("/api/scene").json()
    # declarar el primer ground la apaga en el ACTO (el propio retorno del ground)
    fid = r.json()["features"][0]["id"]
    r = client.post("/api/commands", json={"type": "ground",
                                           "params": {"name": "g", "feature": fid}})
    assert "aviso_estructura" not in r.json()
