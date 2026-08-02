"""Motion study (V3 bloque #6): interpolación de fotogramas, persistencia y
escaneo de colisiones a lo largo del recorrido."""
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document, DocumentError
from apolo.robotics.motion import duration, scan_collisions, values_at


def _arm_into_obstacle():
    """base + brazo (junta prismática en X) y un obstáculo estático en x=150.
    A valor bajo no colisiona; a valor alto el brazo entra en el obstáculo."""
    d = Document()
    base = d.execute("create_box", {"name": "base", "width": 100, "depth": 100, "height": 100})
    arm = d.execute("create_box", {"name": "brazo", "width": 60, "depth": 60, "height": 60})
    d.execute("create_box", {"name": "obst", "width": 60, "depth": 60, "height": 60, "position": {"x": 150}})
    d.execute("add_joint", {
        "name": "desliza", "type": "prismatica", "parent": base, "child": arm,
        "axis": {"x": 1}, "lower": 0, "upper": 200,
    })
    return d


# ------------------------------------------------------------- interpolación
def test_values_at_interpolation():
    kf = [{"t": 0, "values": {"j": 0}}, {"t": 2, "values": {"j": 90}}]
    assert values_at(kf, 1)["j"] == pytest.approx(45)
    assert values_at(kf, 0)["j"] == 0
    assert values_at(kf, -5)["j"] == 0      # antes del primero → constante
    assert values_at(kf, 9)["j"] == 90      # después del último → constante
    assert duration(kf) == 2
    assert values_at([], 1) == {}


# --------------------------------------------------------------- persistencia
def test_set_motion_sorts_and_roundtrips():
    d = _arm_into_obstacle()
    d.set_motion("Carrera", [{"t": 2, "values": {"desliza": 100}}, {"t": 0, "values": {"desliza": 0}}])
    assert [k["t"] for k in d.motion["Carrera"]] == [0, 2]  # ordenado
    d2 = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert d2.motion == d.motion


def test_multiple_named_studies_coexist():
    d = _arm_into_obstacle()
    d.set_motion("A", [{"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 50}}])
    d.set_motion("B", [{"t": 0, "values": {"desliza": 50}}, {"t": 1, "values": {"desliza": 0}}])
    assert set(d.motion) == {"A", "B"}
    d.set_motion("A", [])           # lista vacía → borra el estudio
    assert set(d.motion) == {"B"}
    d.delete_motion("B")
    assert d.motion == {}


def test_migration_old_list_motion():
    # un manifest viejo guardaba el motion como UNA lista → migra a {"Estudio 1": [...]}
    import json, io, zipfile

    d = _arm_into_obstacle()
    raw = d.to_apolo_bytes()
    buf = io.BytesIO(raw)
    with zipfile.ZipFile(buf) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        others = {n: zf.read(n) for n in zf.namelist() if n != "manifest.json"}
    manifest["motion"] = [{"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 50}}]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for n, b in others.items():
            zf.writestr(n, b)
    d2 = Document.from_apolo_bytes(out.getvalue())
    assert list(d2.motion) == ["Estudio 1"]
    assert [k["t"] for k in d2.motion["Estudio 1"]] == [0, 1]


def test_set_motion_validation():
    d = Document()
    with pytest.raises(DocumentError):
        d.set_motion("X", [{"values": {"j": 0}}])           # falta t
    with pytest.raises(DocumentError):
        d.set_motion("X", [{"t": -1, "values": {}}])         # t negativo
    with pytest.raises(DocumentError):
        d.set_motion("  ", [{"t": 0, "values": {}}])         # nombre vacío


def test_set_motion_rechaza_formato_plano():
    """El bug real (2026-08-01): juntas al NIVEL SUPERIOR del fotograma se aceptaban en
    silencio, values_at() devolvía {} en todo t y el estudio 'reproducía' sin mover nada
    (UI y motion.gif estáticos sin error)."""
    d = _arm_into_obstacle()
    with pytest.raises(DocumentError, match="ANIDADOS"):
        d.set_motion("X", [{"t": 0, "desliza": 50}])          # clave suelta arriba
    with pytest.raises(DocumentError, match="desconocidas"):
        d.set_motion("X", [{"t": 0, "values": {"no_existe": 1}}])   # junta inexistente
    with pytest.raises(DocumentError, match="no mueve"):
        d.set_motion("X", [{"t": 0, "values": {}}, {"t": 1, "values": {}}])  # todo vacío
    with pytest.raises(DocumentError, match="numérico"):
        d.set_motion("X", [{"t": 0, "values": {"desliza": "alto"}}])  # valor no numérico
    assert d.motion == {}                                    # nada quedó persistido


def test_api_motion_rechaza_formato_plano():
    api.DOC = _arm_into_obstacle()
    client = TestClient(api.app)
    r = client.put("/api/motion", json={"name": "Mal", "keyframes": [
        {"t": 0, "desliza": 0}, {"t": 1, "desliza": 50}]})
    assert r.status_code == 400
    assert "values" in r.json()["detail"]                    # el error enseña el formato
    assert client.get("/api/motion").json() == {"studies": []}


def test_api_motion_estudio_viejo_sin_values_da_400():
    """Un estudio persistido en formato viejo (sin 'values' en ningún fotograma, p. ej.
    cargado de un manifest antiguo que esquiva set_motion) → scan y gif dan 400 accionable
    en vez de un recorrido estático."""
    api.DOC = _arm_into_obstacle()
    api.DOC.motion["Viejo"] = [{"t": 0, "desliza": 0}, {"t": 1, "desliza": 50}]
    client = TestClient(api.app)
    r = client.post("/api/motion/scan", json={"name": "Viejo", "steps": 5})
    assert r.status_code == 400 and "values" in r.json()["detail"]
    r = client.post("/api/motion.gif", json={"name": "Viejo", "steps": 5})
    assert r.status_code == 400 and "values" in r.json()["detail"]


# ------------------------------------------------------------------- scan
def test_scan_detects_collision_along_travel():
    d = _arm_into_obstacle()
    d.set_motion("R", [{"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 170}}])
    cols = scan_collisions(d, d.motion["R"], steps=10)
    assert len(cols) > 0                                # el brazo entra en el obstáculo a media carrera
    assert all("interferencias" in c and c["interferencias"] for c in cols)


def test_scan_no_collision_when_clear():
    d = _arm_into_obstacle()
    d.set_motion("R", [{"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 40}}])
    assert scan_collisions(d, d.motion["R"], steps=10) == []  # nunca llega al obstáculo


def test_scan_empty_without_keyframes():
    d = _arm_into_obstacle()
    assert scan_collisions(d, [], steps=10) == []


# ----------------------------------------- arrastre de cuerpo rígido (V6.8-D)
def _respaldo(arrastrar=True):
    """Espejo del camastro 70: cama (padre) + 2 largueros de respaldo unidos por un
    listón vía FIJADORES (declarados ANTES de la junta). El bug real: sin arrastre,
    el larguero B quedaba congelado en el aire (FK solo mueve hijos declarados)."""
    d = Document()
    cama = d.execute("create_box", {"name": "cama", "width": 400, "depth": 300, "height": 40})
    ra = d.execute("create_box", {"name": "rail_a", "width": 300, "depth": 40, "height": 40,
                                  "position": {"y": -100, "z": 100}})
    rb = d.execute("create_box", {"name": "rail_b", "width": 300, "depth": 40, "height": 40,
                                  "position": {"y": 100, "z": 100}})
    li = d.execute("create_box", {"name": "liston", "width": 40, "depth": 240, "height": 20,
                                  "position": {"z": 130}})
    d.execute("fasten", {"name": "f_ra_li", "a": ra, "b": li, "kind": "perno"})
    d.execute("fasten", {"name": "f_li_rb", "a": li, "b": rb, "kind": "perno"})
    d.execute("add_joint", {"name": "bisagra", "type": "giratoria", "parent": cama,
                            "child": ra, "axis": {"y": 1}, "origin": {"z": 100},
                            "arrastrar": arrastrar})
    return d, cama, ra, rb, li


def test_add_joint_arrastrar_materializa_cuerpo_rigido():
    from apolo.robotics.pose import posed_shapes

    d, cama, ra, rb, li = _respaldo()
    rep = d.joints["bisagra"]["arrastre"]
    assert rep["arrastrados"] == sorted([li, rb]) and rep["frontera"] == []
    assert d.joints[f"jf_bisagra_{li}"]["type"] == "fija"
    assert d.joints[f"jf_bisagra_{rb}"]["parent"] == ra   # colgadas del CONDUCTOR
    # FK: el cuerpo completo se mueve (antes: rail_b congelado en el aire)
    override, warns = posed_shapes(d, {"bisagra": 90})
    assert warns == []
    dz = abs(override[rb].bounding_box().min.Z - d.scene[rb].shape.bounding_box().min.Z)
    assert dz > 50
    # el arrastre SOBREVIVE al regenerate (se recalcula del log, mismo resultado)
    d.regenerate()
    assert f"jf_bisagra_{rb}" in d.joints
    assert d.joints["bisagra"]["arrastre"]["arrastrados"] == sorted([li, rb])


def test_add_joint_arrastrar_false_es_comportamiento_clasico():
    d, cama, ra, rb, li = _respaldo(arrastrar=False)
    assert "arrastre" not in d.joints["bisagra"]
    assert [n for n in d.joints if n.startswith("jf_")] == []


def test_add_joint_arrastrar_disputa_va_a_frontera():
    """Una pieza unida a AMBOS lados (el apoyo_barra del camastro) hace ambiguo todo lo
    conectado a través de ella: NADA disputado se arrastra y el aviso lo explica. El
    fijador del PIVOTE (ra↔cama) no fuga el flood: cada lado excluye el nodo contrario."""
    d = Document()
    cama = d.execute("create_box", {"name": "cama", "width": 400, "depth": 300, "height": 40})
    ra = d.execute("create_box", {"name": "rail_a", "width": 300, "depth": 40, "height": 40,
                                  "position": {"y": -100, "z": 100}})
    li = d.execute("create_box", {"name": "liston", "width": 40, "depth": 240, "height": 20,
                                  "position": {"z": 130}})
    ap = d.execute("create_box", {"name": "apoyo", "width": 40, "depth": 40, "height": 60,
                                  "position": {"x": 150, "z": 70}})
    d.execute("fasten", {"name": "f_ra_li", "a": ra, "b": li, "kind": "perno"})
    d.execute("fasten", {"name": "f_pivote", "a": ra, "b": cama, "kind": "perno"})  # cruza la junta
    d.execute("fasten", {"name": "f_ap_li", "a": ap, "b": li, "kind": "contacto"})   # lado hijo
    d.execute("fasten", {"name": "f_ap_cama", "a": ap, "b": cama, "kind": "contacto"})  # lado padre
    d.execute("add_joint", {"name": "bisagra", "type": "giratoria", "parent": cama,
                            "child": ra, "axis": {"y": 1}, "origin": {"z": 100},
                            "arrastrar": True})
    rep = d.joints["bisagra"]["arrastre"]
    assert rep["arrastrados"] == []                       # la disputa es viral: nada se adivina
    assert rep["frontera"] == sorted([li, ap])
    assert any("disputa" in a for a in rep["avisos"])
    assert [n for n in d.joints if n.startswith("jf_")] == []


def test_add_joint_arrastrar_respeta_juntas_y_tierra():
    d = Document()
    cama = d.execute("create_box", {"name": "cama", "width": 400, "depth": 300, "height": 40})
    ra = d.execute("create_box", {"name": "rail_a", "width": 300, "depth": 40, "height": 40,
                                  "position": {"y": -100, "z": 100}})
    rb = d.execute("create_box", {"name": "rail_b", "width": 300, "depth": 40, "height": 40,
                                  "position": {"y": 100, "z": 100}})
    li = d.execute("create_box", {"name": "liston", "width": 40, "depth": 240, "height": 20,
                                  "position": {"z": 130}})
    d.execute("fasten", {"name": "f_ra_li", "a": ra, "b": li, "kind": "perno"})
    d.execute("fasten", {"name": "f_li_rb", "a": li, "b": rb, "kind": "perno"})
    d.execute("add_joint", {"name": "j_li", "type": "fija", "parent": rb, "child": li})
    d.execute("ground", {"name": "g_rb", "feature": rb})
    d.execute("add_joint", {"name": "bisagra", "type": "giratoria", "parent": cama,
                            "child": ra, "axis": {"y": 1}, "origin": {"z": 100},
                            "arrastrar": True})
    rep = d.joints["bisagra"]["arrastre"]
    assert rep["arrastrados"] == []
    assert any("ya es hijo" in a for a in rep["avisos"])
    assert any("tierra" in a for a in rep["avisos"])


def test_kinematics_payload_sentido_y_arrastre():
    d, cama, ra, rb, li = _respaldo()
    api.DOC = d
    out = TestClient(api.app).get("/api/kinematics").json()
    bis = next(j for j in out["joints"] if j["name"] == "bisagra")
    assert "HORARIA" in bis["sentido"]                    # el signo se LEE, no se calibra
    assert bis["arrastre"]["arrastrados"] == sorted([li, rb])
    jf = next(j for j in out["joints"] if j["name"].startswith("jf_"))
    assert "sentido" not in jf                            # fija no rota


# ----------------------------------------------------------------- API HTTP
def test_api_motion_crud():
    api.DOC = _arm_into_obstacle()
    client = TestClient(api.app)
    assert client.get("/api/motion").json() == {"studies": []}
    r = client.put("/api/motion", json={"name": "Carrera", "keyframes": [
        {"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 170}}]})
    assert r.status_code == 200
    studies = r.json()["studies"]
    assert len(studies) == 1 and studies[0]["name"] == "Carrera" and studies[0]["duration"] == 1
    got = client.get("/api/motion").json()
    assert len(got["studies"][0]["keyframes"]) == 2
    scan = client.post("/api/motion/scan", json={"name": "Carrera", "steps": 10}).json()
    assert len(scan["colisiones"]) > 0
    # un segundo estudio coexiste
    client.put("/api/motion", json={"name": "Otra", "keyframes": [{"t": 0, "values": {"desliza": 0}}]})
    assert {s["name"] for s in client.get("/api/motion").json()["studies"]} == {"Carrera", "Otra"}
    # borrar por nombre
    client.request("DELETE", "/api/motion", json={"name": "Otra"})
    assert {s["name"] for s in client.get("/api/motion").json()["studies"]} == {"Carrera"}
    # validación
    assert client.put("/api/motion", json={"name": "X", "keyframes": [{"values": {}}]}).status_code == 400
