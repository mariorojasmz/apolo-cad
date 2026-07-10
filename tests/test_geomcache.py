"""Caché de geometría por firma (V6.2a): open frío → open caliente.

Contrato (estilo V6.1, primero en rojo): el open CALIENTE (con caché sembrada) reproduce
EXACTO el frío, deja el documento íntegro, conserva el instancing, y ante CUALQUIER
corrupción de la caché cae a replay frío limpio sin excepción. La caché nunca es
autoritativa — el .apolo lo es.
"""

from __future__ import annotations

import pickle

from apolo.doc.document import Document
from apolo.doc.geomcache import GEOM_CACHE_EPOCH, pack, unpack


def _model(n: int = 8) -> tuple[Document, list[str]]:
    """Modelo con instancias (cajas), un patrón, una variable, una junta y un grupo."""
    doc = Document("gc")
    doc.execute("set_variable", {"name": "W", "expression": "50"})
    seeds: list[str] = []
    for i in range(n):
        seeds.append(
            doc.execute("create_box", {
                "name": f"b{i}",
                "width": "=W" if i == 0 else 40 + i,
                "depth": 30, "height": 20, "position": {"x": i * 80},
            })
        )
    doc.execute("pattern_group", {"source": seeds[0], "count": 4, "spacing": {"y": 90}})
    if n >= 3:
        doc.execute("add_joint", {
            "name": "j1", "type": "giratoria", "parent": seeds[1], "child": seeds[2],
            "origin": {"x": 0, "y": 0, "z": 0}, "axis": {"x": 0, "y": 0, "z": 1},
            "lower": 0, "upper": 90,
        })
        doc.execute("create_group", {"name": "G", "members": [seeds[1], seeds[2]]})
    return doc, seeds


def _assert_scene_equal(a: Document, b: Document) -> None:
    assert sorted(a.scene) == sorted(b.scene)
    for fid in b.scene:
        assert abs(a.scene[fid].shape.volume - b.scene[fid].shape.volume) < 1e-6
        ab = a.scene[fid].shape.bounding_box()
        bb = b.scene[fid].shape.bounding_box()
        for axis in ("min", "max"):
            for c in ("X", "Y", "Z"):
                assert abs(getattr(getattr(ab, axis), c) - getattr(getattr(bb, axis), c)) < 1e-6


# =========================================================== pack / unpack básicos


def test_pack_unpack_roundtrip():
    doc, _ = _model(6)
    blob = pack(doc)
    assert blob is not None
    out = unpack(blob)
    assert out is not None
    sigs, state, definitions = out
    assert sigs == doc._regen_sigs
    assert isinstance(state, tuple) and len(state) == 8
    assert definitions  # el modelo tiene instancias → definiciones canónicas


def test_pack_empty_doc_is_none():
    assert pack(Document("vacío")) is None


# ================================================================ open caliente


def test_warm_open_equivalence():
    """Caliente vs frío: misma escena/joints/grupos/variables, integridad limpia, y el
    blob CARGA las definiciones (probado limpiando DEFINITIONS antes del warm — el warm no
    replaya, así que solo _try_warm puede reponerlas)."""
    from apolo.commands.registry import DEFINITIONS

    doc, _ = _model(10)
    apolo = doc.to_apolo_bytes()
    warm = unpack(pack(doc))
    assert warm is not None

    cold = Document.from_apolo_bytes(apolo)
    DEFINITIONS.clear()  # el warm debe reponerlas desde el blob, no del ambiente
    hot = Document.from_apolo_bytes(apolo, warm=warm)

    _assert_scene_equal(hot, cold)
    assert set(hot.joints) == set(cold.joints)
    assert {g: sorted(v["members"]) for g, v in hot.groups.items()} == {
        g: sorted(v["members"]) for g, v in cold.groups.items()
    }
    assert hot.variables_resolved == cold.variables_resolved
    # sin violaciones NI degradado → el instancing se preservó (definiciones repuestas)
    assert hot.check_integrity() == []


def test_warm_prefix_replays_only_tail():
    """Caché de N comandos + log de N+3: el warm reanuda del checkpoint y solo replaya la
    cola (3 ejecuciones), reproduciendo el frío."""
    import apolo.doc.document as docmod

    doc, _ = _model(8)
    warm = unpack(pack(doc))  # caché en N comandos
    for i in range(3):
        doc.execute("create_box", {"name": f"x{i}", "width": 25 + i, "position": {"x": 3000 + i * 40}})
    apolo = doc.to_apolo_bytes()

    calls = {"n": 0}
    orig = docmod.execute_command

    def spy(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    docmod.execute_command = spy
    try:
        hot = Document.from_apolo_bytes(apolo, warm=warm)
    finally:
        docmod.execute_command = orig

    assert calls["n"] == 3  # solo la cola, no los N cacheados
    _assert_scene_equal(hot, Document.from_apolo_bytes(apolo))
    assert hot.check_integrity() == []


def test_warm_open_with_catalog_components():
    """Regresión (V6.2, formato v2): un modelo con COMPONENTES de catálogo (create_conveyor)
    tiene wrappers build123d con estado (joints/children) que NO round-trip-ean por pickle.
    El formato v2 serializa el TopoDS crudo (BinTools) → el warm es REAL, no un fallback frío
    silencioso. Sin la corrección, unpack devolvía None y se replayaba en frío sin avisar."""
    import apolo.doc.document as docmod

    doc = Document("conveyor")
    doc.execute("create_conveyor", {"largo": 800, "ancho": 400, "altura": 500, "paso": 100})
    apolo = doc.to_apolo_bytes()
    warm = unpack(pack(doc))
    assert warm is not None  # el modelo con componentes SÍ round-trip-ea (era el bug)

    calls = {"n": 0}
    orig = docmod.execute_command

    def spy(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    docmod.execute_command = spy
    try:
        hot = Document.from_apolo_bytes(apolo, warm=warm)
    finally:
        docmod.execute_command = orig
    assert calls["n"] == 0  # replay REAL de 0 comandos (no fallback frío)
    _assert_scene_equal(hot, Document.from_apolo_bytes(apolo))
    assert hot.check_integrity() == []


def test_warm_full_match_replays_nothing():
    """Caché al día (log sin cambios): 0 ejecuciones de comando en el open caliente."""
    import apolo.doc.document as docmod

    doc, _ = _model(6)
    apolo = doc.to_apolo_bytes()
    warm = unpack(pack(doc))

    calls = {"n": 0}
    orig = docmod.execute_command

    def spy(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    docmod.execute_command = spy
    try:
        hot = Document.from_apolo_bytes(apolo, warm=warm)
    finally:
        docmod.execute_command = orig
    assert calls["n"] == 0
    assert hot.check_integrity() == []


# ============================================================ corrupción → frío


def test_unpack_rejects_corruption():
    doc, _ = _model(5)
    good = pack(doc)
    assert unpack(good) is not None
    assert unpack(None) is None
    assert unpack(b"") is None
    assert unpack(b"esto no es un pickle") is None
    assert unpack(good[: len(good) // 2]) is None  # truncado
    assert unpack(pickle.dumps([1, 2, 3])) is None  # no-dict
    bad_epoch = pickle.loads(good)
    bad_epoch["epoch"] = GEOM_CACHE_EPOCH + 99
    assert unpack(pickle.dumps(bad_epoch)) is None
    bad_ver = pickle.loads(good)
    bad_ver["versions"] = {"build123d": "0.0.0", "ocp": "0.0.0"}
    assert unpack(pickle.dumps(bad_ver)) is None
    bad_struct = pickle.loads(good)
    bad_struct["sigs"] = "no-es-lista"
    assert unpack(pickle.dumps(bad_struct)) is None


def test_bad_warm_never_raises():
    """from_apolo_bytes con un warm basura NO revienta y da el doc correcto (replay frío)."""
    doc, _ = _model(5)
    apolo = doc.to_apolo_bytes()
    cold = Document.from_apolo_bytes(apolo)
    for junk in (("garbage", 123, None), (None, None, None), (["sig-inexistente"], (), {}), 42):
        hot = Document.from_apolo_bytes(apolo, warm=junk)
        _assert_scene_equal(hot, cold)
        assert hot.check_integrity() == []


def test_divergent_sigs_rejected():
    """Una caché cuyas firmas NO son prefijo del log (otro proyecto) se ignora."""
    doc_a, _ = _model(6)
    doc_b, _ = _model(7)  # log distinto
    warm_b = unpack(pack(doc_b))
    apolo_a = doc_a.to_apolo_bytes()
    hot = Document.from_apolo_bytes(apolo_a, warm=warm_b)
    _assert_scene_equal(hot, Document.from_apolo_bytes(apolo_a))
    assert hot.check_integrity() == []


# ============================================================ ProjectStore + warm


def test_store_warm_roundtrip(tmp_path):
    from apolo.projects import ProjectStore

    store = ProjectStore(str(tmp_path / "t.db"))
    doc, _ = _model(8)
    pid = store.create(doc)
    sig = doc._regen_sigs[-1]
    store.save_geom_cache(pid, sig, pack(doc))
    assert store.geom_cache_sig(pid) == sig

    loaded = store.load(pid)  # usa warm internamente
    _assert_scene_equal(loaded, doc)
    assert loaded.check_integrity() == []

    store.delete(pid)  # cascada: borra también la caché
    assert store.geom_cache_sig(pid) is None


def test_kill_switch_skips_warm(tmp_path, monkeypatch):
    from apolo.projects import ProjectStore

    store = ProjectStore(str(tmp_path / "k.db"))
    doc, _ = _model(6)
    pid = store.create(doc)
    store.save_geom_cache(pid, doc._regen_sigs[-1], pack(doc))
    monkeypatch.setenv("APOLO_GEOM_CACHE", "0")
    loaded = store.load(pid)  # NO usa warm; replay frío correcto
    _assert_scene_equal(loaded, doc)
    assert loaded.check_integrity() == []
