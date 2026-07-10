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
    # conectividad resuelta idéntica (mates desplazan geometría → ya cubierto por bbox arriba;
    # esto verifica que las DECLARACIONES también coinciden — V6.2e Fix 3)
    assert set(a.joints) == set(b.joints)
    assert set(a.mates) == set(b.mates)
    assert set(a.fasteners) == set(b.fasteners)
    assert set(a.grounds) == set(b.grounds)


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


# ============================================ V6.2e Fixes 3–6


def test_warm_open_with_mates_positions_match_cold():
    """Fix 3: pack empaca el checkpoint ORGÁNICO (pre-finalización). Un mate desplaza B; la
    cola (un center_in que LEE la posición de B en tiempo de ejecución) debe correr contra la
    geometría PRE-mates, igual que el replay frío. Con el estado POST-mates, C se centraría en
    el sitio equivocado (sobre A, no sobre la posición original de B)."""
    doc = Document("mate")
    a = doc.execute("create_box", {"name": "A", "width": 100, "depth": 100, "height": 40})
    b = doc.execute("create_box", {"name": "B", "width": 40, "depth": 40, "height": 40,
                                   "position": {"x": 500, "y": 300, "z": 200}})
    doc.execute("add_mate", {
        "name": "m1", "type": "coincidente", "feature_a": a, "feature_b": b,
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"},
    })
    warm = unpack(pack(doc))  # caché en el PREFIJO [A, B, mate] — B declarado en x=500
    assert warm is not None
    # cola: C centrado en X sobre B (center_in lee la posición de B al ejecutar = PRE-mates)
    c = doc.execute("create_box", {"name": "C", "width": 20, "depth": 20, "height": 20,
                                   "position": {"x": -999}})
    doc.execute("center_in", {"feature": c, "into": b, "axes": ["x"]})
    apolo = doc.to_apolo_bytes()

    hot = Document.from_apolo_bytes(apolo, warm=warm)
    _assert_scene_equal(hot, Document.from_apolo_bytes(apolo))
    cbb = hot.scene[c].shape.bounding_box()
    assert abs((cbb.min.X + cbb.max.X) / 2 - 500) < 1.0  # sobre la posición PRE-mates de B (~500)


def test_pack_none_if_suppressed():
    """Fix 4: un doc con comandos SUPRIMIDOS (carga tolerante) NO se cachea (el warm reportaría
    suppressed=[] enmascarando el chip y podría servir una escena sin la pieza)."""
    doc, _ = _model(4)
    doc.regen_suppressed = [{"command_id": "c1", "type": "create_box", "error": "boom"}]
    assert pack(doc) is None


def test_warm_seeded_regenerate_raise_falls_back_cold():
    """Fix 5: si el regenerate con la caché SEMBRADA lanza (excepción arbitraria en la cola),
    from_apolo_bytes descarta la caché y replaya en FRÍO, sin propagar la excepción."""
    import apolo.commands.registry as reg
    import apolo.doc.document as docmod  # noqa: F401  (execute_command es de aquí)

    doc, _ = _model(6)
    warm = unpack(pack(doc))
    doc.execute("create_box", {"name": "tail", "width": 33, "position": {"x": 9000}})
    apolo = doc.to_apolo_bytes()

    spec = reg.REGISTRY["create_box"]
    orig = spec.executor
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:  # la 1ª llamada (replay de la cola sembrada) revienta
            raise reg.CommandError("flaky boom (inyectado)")
        return orig(*a, **k)

    spec.executor = flaky
    try:
        hot = Document.from_apolo_bytes(apolo, warm=warm)  # no debe lanzar → fallback frío
    finally:
        spec.executor = orig
    _assert_scene_equal(hot, Document.from_apolo_bytes(apolo))
    assert hot.check_integrity() == []


def test_cold_open_populates_cache(tmp_path):
    """Fix 6: un proyecto que solo se ABRE puebla la caché en el primer open (frío) → el
    segundo open es CALIENTE sin mutaciones de por medio."""
    import apolo.doc.document as docmod

    from apolo.projects import ProjectStore

    store = ProjectStore(str(tmp_path / "f.db"))
    doc, _ = _model(6)
    pid = store.create(doc)
    assert store.geom_cache_sig(pid) is None  # create no puebla la caché

    d1 = store.load(pid)  # 1er open FRÍO → Fix 6 puebla
    assert store.geom_cache_sig(pid) == d1._regen_sigs[-1]

    calls = {"n": 0}
    orig = docmod.execute_command

    def spy(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    docmod.execute_command = spy
    try:
        d2 = store.load(pid)  # 2º open: CALIENTE (0 replays)
    finally:
        docmod.execute_command = orig
    assert calls["n"] == 0
    assert d2.check_integrity() == []


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
