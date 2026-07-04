"""Export DWG (V5.9): conversión DXF→DWG con ODA File Converter (ezdxf.addons.odafc).

Los tests de CONTRATO (error amable sin el conversor, descubrimiento de la carpeta
versionada) corren SIEMPRE; los de conversión REAL exigen ODA instalado (skipif)."""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
import apolo.drawing.dwg as dwg_mod
from apolo.doc import Document
from apolo.drawing.dwg import DwgError, _discover, dxf_to_dwg_bytes

_ODA_OK = _discover()
requires_oda = pytest.mark.skipif(not _ODA_OK, reason="ODA File Converter no instalado")


def _client_con_placa(thread=False):
    api.DOC = Document("dwg-test")
    client = TestClient(api.app)
    client.post("/api/commands", json={"type": "create_box", "params": {
        "name": "Placa", "width": 150, "depth": 100, "height": 15}})
    fid = next(iter(api.DOC.scene))
    if thread:
        client.post("/api/commands", json={"type": "drill_hole", "params": {
            "feature": fid, "position": {"x": 0, "y": 0, "z": 15}, "thread": "M8"}})
    return client, fid


# ------------------------------------------------------- contrato (corre SIEMPRE)
def _sin_oda(monkeypatch):
    monkeypatch.setattr(dwg_mod, "_discover", lambda roots=None: False)


def test_spec_dwg_sin_oda_400(monkeypatch):
    _sin_oda(monkeypatch)
    client, _ = _client_con_placa()
    r = client.post("/api/drawing/spec", json={"format": "dwg"})
    assert r.status_code == 400 and "opendesign.com" in r.json()["detail"]


def test_flat_dwg_sin_oda_400(monkeypatch):
    _sin_oda(monkeypatch)
    api.DOC = Document("dwg-flat")
    client = TestClient(api.app)
    client.post("/api/commands", json={"type": "create_sheet_metal", "params": {
        "ancho": 200, "fondo": 150, "espesor": 2, "lados": ["frente"]}})
    fid = next(iter(api.DOC.scene))
    r = client.get(f"/api/sheetmetal/{fid}/flat.dwg")
    assert r.status_code == 400 and "ODA" in r.json()["detail"]


def test_drawingset_dwg_sin_oda_400(monkeypatch):
    _sin_oda(monkeypatch)
    client, _ = _client_con_placa()
    r = client.get("/api/drawingset.dwg")
    assert r.status_code == 400 and "opendesign.com" in r.json()["detail"]


def test_dxf_to_dwg_sin_oda_raises(monkeypatch):
    _sin_oda(monkeypatch)
    with pytest.raises(DwgError, match="opendesign.com"):
        dxf_to_dwg_bytes(b"0\nEOF\n")


def test_discover_carpeta_versionada(tmp_path):
    # el instalador de ODA crea C:\Program Files\ODA\ODAFileConverter 26.x\ (versionada);
    # se fuerza el escaneo apuntando primero a una ruta inexistente (si hay un ODA real
    # instalado, is_installed() daría True y el glob no se ejercitaría)
    exe = tmp_path / "ODA" / "ODAFileConverter 26.4.0" / "ODAFileConverter.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"fake")
    import ezdxf
    before = ezdxf.options.get("odafc-addon", "win_exec_path")
    try:
        ezdxf.options.set("odafc-addon", "win_exec_path", r"C:\no\existe\ODAFileConverter.exe")
        found = _discover(roots=(str(tmp_path / "ODA"),))
        # con el exe fake, ezdxf lo da por instalado (existencia del archivo)
        assert found is True
        assert "26.4.0" in ezdxf.options.get("odafc-addon", "win_exec_path")
    finally:
        ezdxf.options.set("odafc-addon", "win_exec_path", before)


# --------------------------------------------------- conversión real (skipif ODA)
@requires_oda
def test_spec_dwg_real_magic():
    client, _ = _client_con_placa(thread=True)
    r = client.post("/api/drawing/spec", json={"format": "dwg"})
    assert r.status_code == 200
    assert r.content[:4] == b"AC10"  # DWG magic (AC1032 = R2018)
    assert r.headers["content-type"].startswith("application/acad")


@requires_oda
def test_dwg_roundtrip_capas():
    # convertir de vuelta con odafc.readfile y verificar que las capas del plano viven
    import tempfile
    from pathlib import Path

    from ezdxf.addons import odafc

    client, _ = _client_con_placa(thread=True)
    r = client.post("/api/drawing/spec", json={"format": "dwg"})
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "plano.dwg"
        p.write_bytes(r.content)
        doc = odafc.readfile(str(p))
    layers = {ly.dxf.name for ly in doc.layers}
    assert {"VISIBLE", "COTAS", "ROSCA"} <= layers  # la ROSCA viene del drill M8


@requires_oda
def test_flat_dwg_real():
    api.DOC = Document("dwg-flat-real")
    client = TestClient(api.app)
    client.post("/api/commands", json={"type": "create_sheet_metal", "params": {
        "ancho": 200, "fondo": 150, "espesor": 2, "lados": ["frente"]}})
    fid = next(iter(api.DOC.scene))
    r = client.get(f"/api/sheetmetal/{fid}/flat.dwg")
    assert r.status_code == 200 and r.content[:4] == b"AC10"


@requires_oda
def test_drawingset_dwg_zip():
    client, _ = _client_con_placa()
    r = client.get("/api/drawingset.dwg")
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert names and all(n.endswith(".dwg") for n in names)
    assert zf.read(names[0])[:4] == b"AC10"
