"""Caché de geometría con cadenas (plan teselado-rapido, F2).

La piloto 74 nunca tuvo caché: `pack` devolvía None porque BinTools (versiones 1, 2 y 4, la
actual) escribe la cadena de `create_chain` —la fusión de 30+ copias colocadas de un rodillo y
unas placas— con un índice de curva que luego no puede leer, cruda y copiada. La caché la
escribe en VERSION_3 de último recurso. Además el blob no lleva la malla de render (D3,
descartado): sin eso, su tamaño dependía de si hubo un render antes del autosave.
"""

from __future__ import annotations

import pytest
from build123d import Box
from build123d.persistence import deserialize_shape, serialize_shape

import apolo.doc.document as docmod
from apolo.brep_io import serialize_robust
from apolo.doc.document import Document
from apolo.doc.geomcache import pack, unpack


@pytest.fixture(scope="module")
def doc_cadena() -> Document:
    """Dos piñones Z15 a 95,25 mm y su cadena (la misma definición que diez lazos de la 74)."""
    doc = Document("cadena")
    a = doc.execute("insert_component", {"component": "PINON-ASA40-1-Z15"})
    b = doc.execute("insert_component", {"component": "PINON-ASA40-1-Z15", "position": {"x": 95.25}})
    doc.execute("create_chain", {"name": "Cadena", "pinon_a": a, "pinon_b": b})
    return doc


def _cadena(doc: Document):
    return next(f for f in doc.scene.values() if (f.mesh_key or "").startswith("cadena|"))


def _contar_ejecuciones(fn):
    calls = {"n": 0}
    orig = docmod.execute_command

    def spy(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    docmod.execute_command = spy
    try:
        out = fn()
    finally:
        docmod.execute_command = orig
    return out, calls["n"]


def _huella(shape) -> list:
    """Cada cara, en el orden de `faces()` (las zonas de acabado van por índice de cara)."""
    return [(round(f.area, 6), tuple(round(c, 6) for c in f.center())) for f in shape.faces()]


def test_la_cadena_no_round_trip_ea_por_el_camino_del_sandbox(doc_cadena):
    """El síntoma de la F0, tal cual: el BinTools actual (crudo o copiado) no se puede leer.
    Si un OCP futuro lo arregla, este test avisa de que la VERSION_3 ya sobra."""
    forma = _cadena(doc_cadena).shape.wrapped
    with pytest.raises(Exception):
        deserialize_shape(serialize_shape(forma))
    assert serialize_robust(forma) is None
    assert serialize_robust(forma, cache_geometria=True) is not None


def test_un_documento_con_cadena_se_empaca_y_abre_caliente_igual_que_frio(doc_cadena):
    blob = pack(doc_cadena)
    assert blob is not None  # antes: None → la piloto abría siempre en frío
    warm = unpack(blob)
    assert warm is not None
    apolo = doc_cadena.to_apolo_bytes()
    cold = Document.from_apolo_bytes(apolo)
    hot, n = _contar_ejecuciones(lambda: Document.from_apolo_bytes(apolo, warm=warm))
    assert n == 0  # caliente de verdad: ningún comando re-ejecutado
    assert hot._regen_sigs == cold._regen_sigs
    assert sorted(hot.scene) == sorted(cold.scene)
    for fid, f in cold.scene.items():
        h = hot.scene[fid]
        assert h.shape.volume == pytest.approx(f.shape.volume, abs=1e-6)
        assert (h.mesh_key, h.matrix) == (f.mesh_key, f.matrix)
        bh, bc = h.shape.bounding_box(), f.shape.bounding_box()
        for eje in ("X", "Y", "Z"):
            assert getattr(bh.min, eje) == pytest.approx(getattr(bc.min, eje), abs=1e-6)
            assert getattr(bh.max, eje) == pytest.approx(getattr(bc.max, eje), abs=1e-6)
    assert _huella(_cadena(hot).shape) == _huella(_cadena(cold).shape)
    assert hot.check_integrity() == []


def test_el_store_puebla_la_cache_de_la_cadena_y_el_segundo_open_es_caliente(doc_cadena, tmp_path):
    from apolo.projects import ProjectStore

    store = ProjectStore(str(tmp_path / "c.db"))
    pid = store.create(doc_cadena)
    frio = store.load(pid)  # 1er open: frío, y puebla la caché (antes: pack None, nunca)
    assert store.geom_cache_sig(pid) == frio._regen_sigs[-1]
    caliente, n = _contar_ejecuciones(lambda: store.load(pid))
    assert n == 0
    assert _huella(_cadena(caliente).shape) == _huella(_cadena(frio).shape)
    assert caliente.check_integrity() == []


def test_el_blob_no_lleva_la_malla_de_render(doc_cadena):
    """D3 descartado: la malla de render no va a la caché. Tras teselar (como un render_view),
    el blob pesa lo mismo y las formas restauradas no traen triangulación."""
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location

    from apolo.kernel.render_comun import teselar

    antes = pack(doc_cadena)
    for f in doc_cadena.scene.values():
        teselar(f.shape)
    assert all(BRep_Tool.Triangulation_s(c.wrapped, TopLoc_Location()) is not None
               for c in _cadena(doc_cadena).shape.faces())
    despues = pack(doc_cadena)
    assert len(despues) == len(antes)
    _, state, _ = unpack(despues)
    for f in state.scene.values():
        assert all(BRep_Tool.Triangulation_s(c.wrapped, TopLoc_Location()) is None
                   for c in f.shape.faces())


def test_el_camino_del_sandbox_sigue_byte_identico():
    """Sin `cache_geometria`, los bytes son los de `serialize_shape` (con la malla que tenga):
    lo que entrega `run_script` no cambia."""
    caja = Box(10, 20, 30)
    assert serialize_robust(caja.wrapped) == serialize_shape(caja.wrapped)
    caja.mesh(0.5, 0.25)
    con_malla = serialize_robust(caja.wrapped)
    assert con_malla == serialize_shape(caja.wrapped)
    assert len(serialize_robust(caja.wrapped, cache_geometria=True)) < len(con_malla)
