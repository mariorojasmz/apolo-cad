"""FEA de ENSAMBLAJE BONDED (V7.4): gmsh fragment (interfaces compartidas) +
scikit-fem multi-material (E/ν por elemento). Los numéricos exigen el extra [fea]
(skip si no está); el contrato de la API (400 sin solve, vigencia, roundtrip) corre
SIEMPRE."""
import importlib.util

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.fea import FeaError

_FEA_OK = (importlib.util.find_spec("gmsh") is not None
           and importlib.util.find_spec("skfem") is not None)
requires_fea = pytest.mark.skipif(not _FEA_OK, reason="extra [fea] no instalado")

# viga 200×20×20 PARTIDA en dos cajas de 100 pegadas en x=100; F=200 N en −Z en la punta:
# I = 20·20³/12 = 13333.3 mm⁴ · δ = FL³/3EI = 0.2000 mm · σ raíz = FL·(h/2)/I = 30 MPa
LT, SEG, W, HH, FZ = 200.0, 100.0, 20.0, 20.0, 200.0
DELTA_TEO = FZ * LT**3 / (3 * 200000.0 * (W * HH**3 / 12))   # 0.2 mm
SIGMA_ROOT = (FZ * LT) * (HH / 2) / (W * HH**3 / 12)          # 30 MPa


def _two_box(tmp_path, overlap=0.0):
    from build123d import Box, Pos, export_step
    from apolo.fea.mesher import FaceDesc, PieceMesh

    b1 = Pos(SEG / 2, 0, 0) * Box(SEG, W, HH)              # x: 0..100
    b2 = Pos(SEG + SEG / 2 - overlap, 0, 0) * Box(SEG, W, HH)  # x: 100-ov..200-ov
    s1 = str(tmp_path / "b1.step"); export_step(b1, s1)
    s2 = str(tmp_path / "b2.step"); export_step(b2, s2)
    pieces = [PieceMesh(key="b1", step_path=s1), PieceMesh(key="b2", step_path=s2)]

    def descs(shape, xval):
        return [FaceDesc.from_face(f) for f in shape.faces()
                if abs(f.center().X - xval) < 1e-6]

    return pieces, descs(b1, 0.0), descs(b2, 200.0 - overlap)


# --------------------------------------------------- solver bonded anclado a viga
@requires_fea
def test_bonded_cantilever_continuous_and_matches_beam(tmp_path):
    from apolo.fea.mesher import mesh_assembly
    from apolo.fea.solver import solve_assembly_elasticity

    pieces, fixed, load = _two_box(tmp_path)
    msh = str(tmp_path / "asm.msh")
    meta = mesh_assembly(pieces, fixed, {"load_0": load}, msh, mesh_size_mm=4.0)
    assert meta["shared_volumes"] == 0 and not meta["absorbidas"]
    assert {g["key"] for g in meta["piece_groups"]} == {"b1", "b2"}

    pm = [{"name": g["name"], "key": g["key"], "e_mpa": 200000.0, "nu": 0.3,
           "density_kg_mm3": 7.85e-6} for g in meta["piece_groups"]]
    field, per = solve_assembly_elasticity(
        msh, pieces=pm, loads=[{"group": "load_0", "force_n": [0, 0, -FZ]}])

    # la viga bonded se comporta como una sola: δ ±8 %, σ raíz ±20 % (concentración)
    assert field.u_max_mm == pytest.approx(DELTA_TEO, rel=0.08)
    assert SIGMA_ROOT * 0.85 <= field.vm_max <= SIGMA_ROOT * 1.6
    # CONTINUIDAD en la interfaz x=100: |u| suave (nodos compartidos = bonded)
    import numpy as np
    xc = field.coords[0]
    near = np.abs(xc - 100.0) < 3.0
    u_teo_100 = FZ * 100.0**2 * (3 * LT - 100.0) / (6 * 200000.0 * (W * HH**3 / 12))
    assert field.u_mag_nodal[near].mean() == pytest.approx(u_teo_100, rel=0.12)
    # per-piece: la raíz (b1) sufre más que la punta (b2)
    by = {r.key: r for r in per}
    assert by["b1"].vm_max > by["b2"].vm_max


@requires_fea
def test_multimaterial_distinct_fs_sustitucion_and_honest_hardware(tmp_path):
    """Multi-material end-to-end por run_assembly_analysis (UN solve, tres contratos):
    FS distintos por pieza + solape declarado; `calc.sustitucion` REPRODUCE el FS
    gobernante (auditoría V7.4b: antes mezclaba el σy gobernante con el σ_vm GLOBAL de
    otra pieza); hipótesis del herraje HONESTA cuando su peso NO se aplicó."""
    import re as _re

    from apolo.fea.assembly import run_assembly_analysis

    pieces, fixed, load = _two_box(tmp_path, overlap=3.0)   # solape de 3 mm
    pin = [
        {"key": "b1", "name": "Raíz acero", "step_path": pieces[0].step_path,
         "e_mpa": 200000.0, "nu": 0.30, "yield_mpa": 250.0,
         "density_kg_mm3": 7.85e-6, "material": "acero", "volumen_mm3": 40000.0},
        {"key": "b2", "name": "Punta aluminio", "step_path": pieces[1].step_path,
         "e_mpa": 70000.0, "nu": 0.33, "yield_mpa": 95.0,
         "density_kg_mm3": 2.7e-6, "material": "aluminio", "volumen_mm3": 40000.0},
    ]
    res, _ = run_assembly_analysis(
        pin, grupo="probe", fixed=fixed,
        loads=[{"descs": load, "force_n": [0, 0, -FZ]}],
        excluded=[{"name": "Motor 2HP", "masa_kg": 30.0}], substitute_applied=False,
        mesh_size_mm=4.0)

    assert res["shared_volumes"] == 1                       # el solape lo detecta y declara
    fs = {p["feature_id"]: p["fs"] for p in res["piezas"]}
    assert fs["b1"] != pytest.approx(fs["b2"], rel=0.05)    # FS distintos por material
    # la tabla abre con la GOBERNANTE (menor FS primero, None al final)
    assert res["piezas"][0]["fs"] == res["fs"] and res["piezas"][0]["pieza"] == res["pieza_critica"]
    # sustitución = los DOS números de la pieza gobernante → reproduce el FS reportado
    m = _re.fullmatch(r"FS = ([\d.]+) / ([\d.]+)", res["calc"]["sustitucion"])
    assert m, res["calc"]["sustitucion"]
    assert float(m.group(1)) / float(m.group(2)) == pytest.approx(res["fs"], rel=0.02)
    assert float(m.group(2)) == pytest.approx(res["piezas"][0]["sigma_vm_max_mpa"], rel=1e-6)
    # herraje excluido con peso NO aplicado (cargas explícitas) → la hipótesis lo DICE
    h = [x for x in res["hipotesis"] if "herraje" in x.lower()]
    assert h and "NO está incluido" in h[0] and "carga sustituta" not in h[0]
    assert res["excluidos"][0]["peso_incluido"] is False


@requires_fea
def test_budget_exceeded_before_meshing(tmp_path):
    """El presupuesto de tets se estima ANTES de mallar: malla fina en un bbox grande
    → error accionable con la sugerencia de subir mesh_size."""
    from apolo.fea.mesher import mesh_assembly

    pieces, fixed, load = _two_box(tmp_path)
    with pytest.raises(FeaError, match="mesh_size_mm"):
        mesh_assembly(pieces, fixed, {"load_0": load}, str(tmp_path / "x.msh"),
                      mesh_size_mm=0.4)  # ~millones de tets estimados


def test_piece_cap_before_gmsh():
    """El tope de piezas se valida ANTES de tocar gmsh (no necesita el extra [fea])."""
    from apolo.fea.mesher import PieceMesh, mesh_assembly

    pieces = [PieceMesh(key=f"p{i}", step_path="") for i in range(26)]
    with pytest.raises(FeaError, match="tope"):
        mesh_assembly(pieces, [], {}, "x.msh")


@requires_fea
def test_floating_piece_rejected(tmp_path):
    """GUARDA de cuerpo rígido: una pieza SUELTA (no pegada al bastidor anclado) → error
    nombrándola, NUNCA un desplazamiento basura de matriz singular."""
    from build123d import Box, Pos, export_step
    from apolo.fea.mesher import FaceDesc, PieceMesh, mesh_assembly

    b1 = Pos(50, 0, 0) * Box(100, 20, 20)              # x 0..100 (se ancla en x=0)
    b2 = Pos(160, 0, 0) * Box(100, 20, 20)             # x 110..210: SEPARADA 10 mm de b1
    s1 = str(tmp_path / "b1.step"); export_step(b1, s1)
    s2 = str(tmp_path / "b2.step"); export_step(b2, s2)
    pieces = [PieceMesh(key="anclada", step_path=s1), PieceMesh(key="suelta", step_path=s2)]
    fixed = [FaceDesc.from_face(f) for f in b1.faces() if abs(f.center().X - 0.0) < 1e-6]
    load = [FaceDesc.from_face(f) for f in b2.faces() if abs(f.center().X - 210.0) < 1e-6]
    with pytest.raises(FeaError, match="SUELTA"):
        mesh_assembly(pieces, fixed, {"load_0": load}, str(tmp_path / "x.msh"), mesh_size_mm=5.0)


@requires_fea
def test_estado_degrades_on_flecha(tmp_path):
    """El criterio impreso es «FS ≥ min Y δ ≤ L/240»: un bastidor con FS holgado pero
    pasado de flecha debe salir «aviso», no «ok» (auditoría V7.4b). F=1200 N →
    δ≈1.2 mm > L/240=0.833; σy=5000 (respaldo) → FS ≈ 17 ≫ 2."""
    from apolo.fea.assembly import run_assembly_analysis

    pieces, fixed, load = _two_box(tmp_path)
    pin = [{"key": p.key, "name": p.key, "step_path": p.step_path,
            "e_mpa": 200000.0, "nu": 0.30, "yield_mpa": 5000.0,
            "density_kg_mm3": 7.85e-6, "material": "acero", "volumen_mm3": 40000.0}
           for p in pieces]
    res, _ = run_assembly_analysis(
        pin, grupo="flecha", fixed=fixed,
        loads=[{"descs": load, "force_n": [0, 0, -6 * FZ]}], mesh_size_mm=8.0)
    assert res["flecha_ok"] is False
    assert res["fs"] is not None and res["fs"] >= res["fs_min"]
    assert res["estado"] == "aviso"


# --------------------------------------------------------- contrato de API (sin solve)
def _client(doc):
    api.DOC = doc
    return TestClient(api.app)


def test_api_needs_group_or_ids_400():
    client = _client(Document("t"))
    r = client.post("/api/fea/assembly", json={})
    assert r.status_code == 400 and "group" in r.json()["detail"].lower()


def test_api_group_only_hardware_400():
    doc = Document("t")
    h = doc.execute("insert_component", {"component": "PERNO-M12", "position": {"x": 0, "y": 0, "z": 0}})
    doc.execute("create_group", {"name": "Solo herraje", "members": [h]})
    r = _client(doc).post("/api/fea/assembly", json={"group": "Solo herraje"})
    assert r.status_code == 400 and "estructural" in r.json()["detail"].lower()


def test_api_motor_excluded_400():
    """Un MOTORREDUCTOR también es herraje para el FEA (FEA_HARDWARE_CATS, V7.4b):
    su geometría de catálogo es representativa — mallarlo mentiría rigidez y peso.
    Grupo con SOLO el motor → 400 «sin piezas estructurales» = quedó excluido."""
    doc = Document("t")
    m = doc.execute("insert_component", {"component": "MOTOR-075", "position": {"x": 0, "y": 0, "z": 0}})
    doc.execute("create_group", {"name": "Motriz", "members": [m]})
    r = _client(doc).post("/api/fea/assembly", json={"group": "Motriz"})
    assert r.status_code == 400 and "estructural" in r.json()["detail"].lower()


def test_fea_hardware_cats_membership():
    """El conjunto de exclusión FEA cubre lo prometido (motor/chumaceras/tuercas…)
    SIN tocar HARDWARE_CATS (semántica de interferencia intacta)."""
    from apolo.library.checks import FEA_HARDWARE_CATS, HARDWARE_CATS

    assert HARDWARE_CATS == {"tornilleria", "rodamientos", "pernos"}
    assert {"motorreductores", "motorreductores_sinfin", "chumaceras",
            "tuercas", "tensores_trotadora"} <= FEA_HARDWARE_CATS
    assert HARDWARE_CATS <= FEA_HARDWARE_CATS
    assert "perfiles" not in FEA_HARDWARE_CATS and "tubos_estructurales" not in FEA_HARDWARE_CATS


def test_api_no_ground_no_fixed_400():
    doc = Document("t")
    a = doc.execute("create_box", {"name": "Larguero A36", "width": 40, "depth": 40, "height": 200})
    b = doc.execute("create_box", {"name": "Pata A36", "width": 40, "depth": 40, "height": 200,
                                   "position": {"x": 100}})
    doc.execute("create_group", {"name": "Estructura", "members": [a, b]})
    r = _client(doc).post("/api/fea/assembly", json={"group": "Estructura"})
    assert r.status_code == 400 and "empotramiento" in r.json()["detail"].lower()


def test_api_manifest_roundtrip_group_key():
    doc = Document("t")
    doc.set_fea_result("group:Estructura", {
        "grupo": "Estructura", "tipo": "ensamblaje_bonded", "fs": 3.4, "estado": "ok",
        "volumen_mm3": 50000.0, "piezas_fids": ["c1"]})
    clone = Document.from_apolo_bytes(doc.to_apolo_bytes(), regenerate=False)
    assert clone.fea["group:Estructura"]["fs"] == 3.4
    assert clone.fea["group:Estructura"]["tipo"] == "ensamblaje_bonded"


def test_fea_rules_render_convergencia():
    """La memoria imprime la serie de CONVERGENCIA de malla (E3.7): runs previos +
    vigente; con historial el cupo de piezas baja a 5 (tope de 12 filas del calc_report)."""
    doc = Document("t")
    a = doc.execute("create_box", {"name": "Larguero", "width": 40, "depth": 40, "height": 200})
    vol = float(doc.scene[a].shape.volumen if hasattr(doc.scene[a].shape, 'volumen') else doc.scene[a].shape.volume)
    api.DOC = doc
    doc.set_fea_result("group:B", {
        "grupo": "B", "tipo": "ensamblaje_bonded", "fs": 64.61, "estado": "ok",
        "mesh_size_mm": 35.0, "desplazamiento_max_mm": 0.023, "pieza_critica": "Larguero",
        "volumen_mm3": vol, "piezas_fids": [a], "detalle": "ok",
        "calc": {"titulo": "x", "fs": 64.61},
        "piezas": [{"pieza": f"P{i}", "sigma_vm_max_mpa": 1.0, "fs": 100.0 + i,
                    "estado": "ok"} for i in range(8)],
        "hipotesis": ["ensamblaje PEGADO (bonded)", "alcance: prueba acotada"],
        "convergencia": [{"mesh_size_mm": 60.0, "n_tets": 15826, "fs": 93.52,
                          "pieza_critica": "Pata A36", "desplazamiento_max_mm": 0.0213}]})
    reglas = [r for r in api._fea_rules() if r["regla"].startswith("FEA bastidor")]
    tabla = reglas[0]["tabla"]
    # las hipótesis pasan a la regla → bloque «HIPÓTESIS Y ALCANCE» de la memoria
    assert reglas[0]["hipotesis"] == ["ensamblaje PEGADO (bonded)", "alcance: prueba acotada"]
    assert any("CONVERGENCIA" in f for f in tabla)
    assert any("60 mm" in f and "93.52" in f for f in tabla)          # el run previo
    assert any("35 mm" in f and "VIGENTE" in f for f in tabla)        # el vigente
    assert len(tabla) <= 12                                           # cabe en la página
    assert any("y 3 pieza(s) más" in f for f in tabla)                # cupo 5 con historial


def test_fea_rules_group_vigencia_missing_piece():
    doc = Document("t")
    a = doc.execute("create_box", {"name": "Larguero", "width": 40, "depth": 40, "height": 200})
    vol = float(doc.scene[a].shape.volume)
    api.DOC = doc
    doc.set_fea_result("group:Estructura", {
        "grupo": "Estructura", "tipo": "ensamblaje_bonded", "fs": 3.0, "estado": "ok",
        "volumen_mm3": vol, "piezas_fids": [a], "calc": {"titulo": "x", "fs": 3.0},
        "detalle": "ok"})
    reglas = api._fea_rules()
    assert reglas and reglas[0]["estado"] == "ok" and reglas[0]["regla"].startswith("FEA bastidor")
    # la pieza desaparece de la escena → la regla degrada a aviso (vigencia)
    doc.scene.pop(a)
    reglas = api._fea_rules()
    assert reglas[0]["estado"] == "aviso" and "existen" in reglas[0]["detalle"]


# --------------------------------------------------------------- E2E por la API
@requires_fea
def test_api_e2e_column_bonded():
    doc = Document("asm-e2e")
    pata = doc.execute("create_box", {"name": "Pata A36", "width": 30, "depth": 30,
                                      "height": 100, "position": {"z": 50}})       # z 0..100
    cama = doc.execute("create_box", {"name": "Cama mesa A36", "width": 30, "depth": 30,
                                      "height": 20, "position": {"z": 110}})       # z 100..120
    perno = doc.execute("insert_component", {"component": "PERNO-M12",
                                             "position": {"x": 40, "y": 0, "z": 110}})
    doc.execute("create_group", {"name": "Estructura", "members": [pata, cama, perno]})
    doc.grounds["g1"] = {"feature": pata}   # pata anclada a piso
    # run PREVIO simulado con OTRO mesh → debe pasar al historial de CONVERGENCIA
    doc.set_fea_result("group:Estructura", {
        "grupo": "Estructura", "tipo": "ensamblaje_bonded", "mesh_size_mm": 99.0,
        "n_tets": 111, "fs": 1.23, "pieza_critica": "Pata A36",
        "desplazamiento_max_mm": 0.5, "volumen_mm3": 1.0, "piezas_fids": [pata]})
    client = _client(doc)
    r = client.post("/api/fea/assembly", json={"group": "Estructura", "carga_kg": 50,
                                               "self_weight": True, "mesh_size_mm": 6.0,
                                               "nota": "alcance de prueba"})
    assert r.status_code == 200, r.json()
    res = r.json()
    # convergencia: el run previo (99 mm) queda en el historial del vigente (6 mm)
    assert res["convergencia"][0]["mesh_size_mm"] == 99.0
    assert any("alcance de prueba" in h for h in res["hipotesis"])
    assert res["tipo"] == "ensamblaje_bonded" and res["n_piezas"] == 2
    assert {p["feature_id"] for p in res["piezas"]} == {pata, cama}
    assert res["fs"] is not None and res["estado"] in ("ok", "aviso", "error")
    # el perno quedó EXCLUIDO y, en la rama AUTO (carga sobre la cama), su peso SÍ
    # entró como carga sustituta — y la hipótesis lo declara con verdad
    assert len(res["excluidos"]) == 1 and res["excluidos"][0]["peso_incluido"] is True
    h = [x for x in res["hipotesis"] if "herraje" in x.lower()]
    assert h and "carga sustituta" in h[0]
    # la regla entra a la memoria con tabla por pieza
    reglas = [x for x in client.post("/api/checks", json={}).json()["estructura"]
              if x["regla"].startswith("FEA bastidor")]
    assert reglas and reglas[0].get("calc") and reglas[0].get("tabla")
    # fringe cacheado sin re-resolver
    assert client.get("/api/fea/group/Estructura/fringe.png").content[:8] == b"\x89PNG\r\n\x1a\n"
