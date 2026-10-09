"""El FEA bonded DECLARA las uniones empernadas que pega (plan `docs/plans/fea-chapa-empernada.md`,
D8). El ensamblaje se analiza PEGADO: para una soldadura es la hipótesis correcta; para un perno
es más rígido que la junta real (sin deslizamiento ni separación) y el resumen debe decirlo.

`services/fea_setup.py::bolted_joints_in_mesh` cuenta los fasteners `perno` cuyas DOS piezas
entran a la malla; la API arma la línea de hipótesis. El conteo corre siempre (sin gmsh); el
análisis por la API exige el extra [fea].
"""
import importlib.util

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.api.fea_runs import FeaAssemblyIn, _hipotesis_empernadas
from apolo.doc import Document
from apolo.services.fea_setup import prepare_assembly, resolve_assembly_scope

_FEA_OK = (importlib.util.find_spec("gmsh") is not None
           and importlib.util.find_spec("skfem") is not None)
requires_fea = pytest.mark.skipif(not _FEA_OK, reason="extra [fea] no instalado")


def _pata_y_cama(doc):
    """Pata (z 0..100, anclada) y cama (z 100..120) en contacto, en el grupo «Estructura»."""
    pata = doc.execute("create_box", {"name": "Pata A36", "width": 30, "depth": 30,
                                      "height": 100, "position": {"z": 50}})
    cama = doc.execute("create_box", {"name": "Cama mesa A36", "width": 30, "depth": 30,
                                      "height": 20, "position": {"z": 110}})
    doc.execute("ground", {"name": "g1", "feature": pata})
    return pata, cama


def _preparar(doc, tmp_path, **body):
    body = FeaAssemblyIn(group="Estructura", **body)
    fids, grupo = resolve_assembly_scope(doc, body)
    return prepare_assembly(doc, body, fids, grupo, str(tmp_path))


def test_cuenta_solo_pernos_entre_piezas_malladas(tmp_path):
    """Perno entre dos piezas del grupo → cuenta. Soldadura → no (pegado es su hipótesis).
    Perno contra el herraje excluido o contra una pieza fuera del grupo → no hay junta en la
    malla. Pegado y contacto tampoco."""
    doc = Document("pernos")
    pata, cama = _pata_y_cama(doc)
    viga = doc.execute("create_box", {"name": "Viga A36", "width": 30, "depth": 30,
                                      "height": 20, "position": {"x": 30, "z": 110}})
    herraje = doc.execute("insert_component", {"component": "PERNO-M12",
                                               "position": {"x": 0, "y": 40, "z": 110}})
    fuera = doc.execute("create_box", {"name": "Soporte ajeno", "width": 30, "depth": 30,
                                       "height": 20, "position": {"x": 60, "z": 110}})
    doc.execute("create_group", {"name": "Estructura", "members": [pata, cama, viga, herraje]})
    for nombre, a, b, kind in (("p_pata_cama", pata, cama, "perno"),
                               ("s_cama_viga", cama, viga, "soldadura"),
                               ("p_cama_herraje", cama, herraje, "perno"),
                               ("p_viga_fuera", viga, fuera, "perno"),
                               ("g_pata_viga", pata, viga, "pegado"),
                               ("c_pata_herraje", pata, herraje, "contacto")):
        doc.execute("fasten", {"name": nombre, "a": a, "b": b, "kind": kind})
    params = _preparar(doc, tmp_path)
    assert set(params["struct_ids"]) == {pata, cama, viga}      # el herraje quedó fuera
    assert params["uniones_empernadas"] == 1


def test_join_bolted_cuenta_y_su_tornilleria_queda_fuera(tmp_path):
    """El `jb_*` que declara `join_bolted` es un `perno` entre las dos placas; los pernos y
    tuercas que inserta son herraje (fuera de la malla) y no suman uniones."""
    doc = Document("jb")
    a = doc.execute("create_box", {"name": "Placa A", "width": 200, "depth": 100, "height": 10,
                                   "position": {"z": 5}})
    b = doc.execute("create_box", {"name": "Placa B", "width": 200, "depth": 100, "height": 10,
                                   "position": {"z": 15}})
    jb = doc.execute("join_bolted", {"a": a, "b": b, "size": "M12", "count": 3})
    doc.execute("ground", {"name": "g1", "feature": a})
    doc.execute("create_group", {"name": "Estructura", "members": [a, b, jb]})
    assert [f["kind"] for f in doc.fasteners.values()] == ["perno"]
    params = _preparar(doc, tmp_path)
    assert set(params["struct_ids"]) == {a, b} and len(params["excluded"]) == 6
    assert params["uniones_empernadas"] == 1


def test_sin_pernos_cero(tmp_path):
    doc = Document("soldado")
    pata, cama = _pata_y_cama(doc)
    doc.execute("create_group", {"name": "Estructura", "members": [pata, cama]})
    doc.execute("fasten", {"name": "s1", "a": pata, "b": cama, "kind": "soldadura"})
    assert _preparar(doc, tmp_path)["uniones_empernadas"] == 0


def test_texto_singular_y_plural():
    uno = _hipotesis_empernadas(1)
    assert uno.startswith("1 unión empernada modelada PEGADA sobre su superficie de contacto")
    assert "sin deslizamiento ni separación" in uno and "el perno se verifica aparte" in uno
    assert "(engineering_check)" in uno
    tres = _hipotesis_empernadas(3)
    assert tres.startswith("3 uniones empernadas modeladas PEGADAS sobre sus superficies")
    assert "más rígidas que las juntas reales" in tres and "los pernos se verifican" in tres


# ----------------------------------------------------------------------- por la API
@requires_fea
@pytest.mark.parametrize("kind", ["perno", "soldadura"])
def test_api_declara_el_perno_y_no_la_soldadura(kind):
    doc = Document(f"api-{kind}")
    pata, cama = _pata_y_cama(doc)
    doc.execute("create_group", {"name": "Estructura", "members": [pata, cama]})
    doc.execute("fasten", {"name": "union", "a": pata, "b": cama, "kind": kind, "size": "M12"}
                if kind == "perno" else {"name": "union", "a": pata, "b": cama, "kind": kind})
    api.DOC = doc
    r = TestClient(api.app).post("/api/fea/assembly", json={
        "group": "Estructura", "carga_kg": 50, "mesh_size_mm": 10.0, "save": False})
    assert r.status_code == 200, r.text
    hip = r.json()["hipotesis"]
    empernadas = [h for h in hip if "empernada" in h]
    if kind == "perno":
        assert empernadas == [_hipotesis_empernadas(1)]
    else:
        assert empernadas == []
    assert any(h.startswith("ensamblaje PEGADO (bonded)") for h in hip)   # la de siempre sigue
