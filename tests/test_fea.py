"""FEA estático lineal (V5.6): gmsh (malla tet) + scikit-fem (P2).

Los tests numéricos exigen el extra [fea] (skip si no está); los de contrato de la
API (400 amigable sin dependencias, selectores, persistencia) corren SIEMPRE.
"""
import importlib.util

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.fea import FeaError
from apolo.fea.static import _estado

_FEA_OK = (importlib.util.find_spec("gmsh") is not None
           and importlib.util.find_spec("skfem") is not None)
requires_fea = pytest.mark.skipif(not _FEA_OK, reason="extra [fea] no instalado")

# viga en voladizo 100×10×10 acero, F=100 N en −Z en la punta (anclas del plan):
# I = 833.33 mm⁴ · δ = FL³/3EI = 0.2000 mm · σ a media luz = 6F(L/2)/(bh²) = 30 MPa
L, B, H, F = 100.0, 10.0, 10.0, 100.0
DELTA_TEO = 0.2000
SIGMA_MID = 30.0


def _export_box(tmp_path, w=L, d=B, h=H) -> str:
    from build123d import Box, Pos, export_step

    shape = Pos(w / 2, 0, 0) * Box(w, d, h)
    step = str(tmp_path / "pieza.step")
    export_step(shape, step)
    return step, shape


def _descs(shape, x_val):
    from apolo.fea.mesher import FaceDesc

    return [FaceDesc.from_face(f) for f in shape.faces()
            if abs(f.center().X - x_val) < 1e-6]


# --------------------------------------------------------------- solver anclado
@requires_fea
def test_viga_voladizo_anclada(tmp_path):
    from apolo.fea.static import run_static_analysis

    step, shape = _export_box(tmp_path)
    resumen, field = run_static_analysis(
        step, pieza="viga", fixed=_descs(shape, 0.0),
        loads=[{"descs": _descs(shape, L), "force_n": [0, 0, -F]}],
        e_mpa=200000, yield_mpa=250, density_kg_mm3=7.85e-6, material="acero",
        mesh_size_mm=2.5,
    )
    assert 0.19 <= resumen["desplazamiento_max_mm"] <= 0.212      # δ ±5 % (+cortante)
    assert 55 <= resumen["sigma_vm_max_mpa"] <= 90                # raíz 60 + concentración
    assert resumen["max_en_encastre"] is True
    assert resumen["estado"] == "ok" and resumen["fs"] > 2.5
    assert resumen["calc"]["fs"] == resumen["fs"]
    assert any("P2" in h for h in resumen["hipotesis"])
    # σ_vm a media luz (lejos de la singularidad) = 30 MPa ±8 %
    import numpy as np
    x = field.coords[0]
    mid = np.abs(x - L / 2) < 3.0
    vm_mid = field.vm_nodal[mid].max()
    assert vm_mid == pytest.approx(SIGMA_MID, rel=0.08)


@requires_fea
def test_traccion_pura_exacta(tmp_path):
    # barra 20×20×100, F=10 kN axial: σ = F/A = 25 MPa, δ = FL/EA = 0.0125 mm
    from apolo.fea.static import run_static_analysis

    step, shape = _export_box(tmp_path, w=100, d=20, h=20)
    resumen, field = run_static_analysis(
        step, pieza="barra", fixed=_descs(shape, 0.0),
        loads=[{"descs": _descs(shape, 100.0), "force_n": [10000, 0, 0]}],
        e_mpa=200000, yield_mpa=250, density_kg_mm3=7.85e-6, material="acero",
        mesh_size_mm=6.0,
    )
    assert resumen["desplazamiento_max_mm"] == pytest.approx(0.0125, rel=0.03)
    import numpy as np
    x = field.coords[0]
    mid = np.abs(x - 50.0) < 8.0
    assert field.vm_nodal[mid].mean() == pytest.approx(25.0, rel=0.03)


@requires_fea
def test_presion_equivale_a_compresion(tmp_path):
    # p=25 MPa entrante en x=100 ≡ compresión axial: δ = pL/E = 0.0125 mm
    from apolo.fea.static import run_static_analysis

    step, shape = _export_box(tmp_path, w=100, d=20, h=20)
    resumen, _ = run_static_analysis(
        step, pieza="barra", fixed=_descs(shape, 0.0),
        loads=[{"descs": _descs(shape, 100.0), "pressure_mpa": 25.0}],
        e_mpa=200000, yield_mpa=250, density_kg_mm3=7.85e-6, material="acero",
        mesh_size_mm=6.0,
    )
    assert resumen["desplazamiento_max_mm"] == pytest.approx(0.0125, rel=0.05)


@requires_fea
def test_peso_propio_viga(tmp_path):
    # voladizo bajo peso propio: q = ρ·g·A → δ = qL⁴/8EI = 5.78e-4 mm
    from apolo.fea.static import run_static_analysis

    step, shape = _export_box(tmp_path)
    resumen, _ = run_static_analysis(
        step, pieza="viga", fixed=_descs(shape, 0.0), loads=[],
        e_mpa=200000, yield_mpa=250, density_kg_mm3=7.85e-6, material="acero",
        self_weight=True, mesh_size_mm=2.5,
    )
    q = 7.85e-6 * 9.81 * B * H                 # N/mm
    delta = q * L**4 / (8 * 200000 * B * H**3 / 12)
    assert resumen["desplazamiento_max_mm"] == pytest.approx(delta, rel=0.10)


@requires_fea
def test_sin_cargas_rechazado(tmp_path):
    from apolo.fea.static import run_static_analysis

    step, shape = _export_box(tmp_path)
    with pytest.raises(FeaError, match="[Ss]in cargas"):
        run_static_analysis(step, pieza="x", fixed=_descs(shape, 0.0), loads=[],
                            e_mpa=200000, yield_mpa=250, density_kg_mm3=7.85e-6,
                            material="acero")


@requires_fea
def test_cap_de_tets(tmp_path):
    from apolo.fea.mesher import mesh_step

    step, shape = _export_box(tmp_path)
    with pytest.raises(FeaError, match="mesh_size_mm"):
        mesh_step(step, {"fixed": _descs(shape, 0.0)}, str(tmp_path / "m.msh"),
                  mesh_size_mm=0.4)  # ~millones de tets → cap


def test_estado_por_fs():
    assert _estado(3.0, 2.0) == "ok"
    assert _estado(1.5, 2.0) == "aviso"
    assert _estado(1.0, 2.0) == "error"
    assert _estado(None, 2.0) == "aviso"


# ------------------------------------------------------------- contrato de API
def _client_con_viga():
    api.DOC = Document("fea-api")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_box", "params": {
        "name": "Viga acero", "width": 100, "depth": 10, "height": 10}})
    fid = r.json()["features"][0]["id"]
    return client, fid


_BODY = {
    "fixed": {"mode": "cara", "face": "min_x"},
    "loads": [{"selector": {"mode": "cara", "face": "max_x"}, "force_n": [0, 0, -100]}],
    "mesh_size_mm": 3.5,
}


def test_api_pieza_inexistente_404():
    client, _ = _client_con_viga()
    r = client.post("/api/fea/static", json={"feature_id": "nope", **_BODY})
    assert r.status_code == 404


def test_api_selector_invalido_400():
    client, fid = _client_con_viga()
    r = client.post("/api/fea/static", json={
        "feature_id": fid, "fixed": {"mode": "noexiste"}, "loads": []})
    assert r.status_code == 400 and "selector" in r.json()["detail"].lower()


def test_api_dependencia_ausente_400(monkeypatch):
    # corre SIEMPRE: simula el extra [fea] sin instalar → 400 con el pip install
    import apolo.fea.static as static_mod

    def _sin_deps():
        raise FeaError("FEA no disponible: ejecuta `pip install gmsh scikit-fem meshio`")

    monkeypatch.setattr(static_mod, "_require_fea", _sin_deps)
    client, fid = _client_con_viga()
    r = client.post("/api/fea/static", json={"feature_id": fid, **_BODY})
    assert r.status_code == 400 and "pip install" in r.json()["detail"]


def test_api_material_sin_yield_400():
    client, fid = _client_con_viga()
    api.DOC.set_material(fid, "pvc")
    r = client.post("/api/fea/static", json={"feature_id": fid, **_BODY})
    assert r.status_code == 400 and "yield_mpa" in r.json()["detail"]


def test_manifest_roundtrip():
    doc = Document("fea-manifest")
    doc.set_fea_result("c1", {"pieza": "Viga", "fs": 3.2, "estado": "ok",
                              "volumen_mm3": 10000.0})
    clone = Document.from_apolo_bytes(doc.to_apolo_bytes(), regenerate=False)
    assert clone.fea["c1"]["fs"] == 3.2
    doc.set_fea_result("c1", None)
    assert "c1" not in doc.fea


@requires_fea
def test_api_flujo_completo_y_staleness():
    client, fid = _client_con_viga()
    r = client.post("/api/fea/static", json={"feature_id": fid, **_BODY})
    assert r.status_code == 200
    res = r.json()
    assert res["desplazamiento_max_mm"] == pytest.approx(DELTA_TEO, rel=0.06)
    assert res["estado"] == "ok" and res["volumen_mm3"] == pytest.approx(10000, rel=1e-3)
    # persistido → GET y regla en /api/checks
    assert client.get(f"/api/fea/{fid}").status_code == 200
    reglas = [x for x in client.post("/api/checks", json={}).json()["estructura"]
              if x["regla"].startswith("FEA")]
    assert reglas and reglas[0]["estado"] == "ok" and reglas[0]["calc"]["fs"] == res["fs"]
    # staleness: la geometría cambia → la regla degrada a aviso
    client.put(f"/api/commands/{fid}", json={"params": {
        "name": "Viga acero", "width": 120, "depth": 10, "height": 10}})
    reglas = [x for x in client.post("/api/checks", json={}).json()["estructura"]
              if x["regla"].startswith("FEA")]
    assert reglas[0]["estado"] == "aviso" and "cambió" in reglas[0]["detalle"]


@requires_fea
def test_api_save_false_no_persiste():
    client, fid = _client_con_viga()
    r = client.post("/api/fea/static", json={"feature_id": fid, **_BODY, "save": False})
    assert r.status_code == 200
    assert client.get(f"/api/fea/{fid}").status_code == 404


@requires_fea
def test_api_fringe_png():
    pytest.importorskip("vtk")
    client, fid = _client_con_viga()
    api._LAST_FEA_FIELD.clear()  # caché de proceso: otro test pudo dejar un campo
    assert client.get(f"/api/fea/{fid}/fringe.png").status_code == 404  # sin solve aún
    r = client.post("/api/fea/static.png", json={"feature_id": fid, **_BODY})
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    # el campo queda cacheado → fringe sin re-resolver
    r2 = client.get(f"/api/fea/{fid}/fringe.png")
    assert r2.status_code == 200 and r2.content[:8] == b"\x89PNG\r\n\x1a\n"
