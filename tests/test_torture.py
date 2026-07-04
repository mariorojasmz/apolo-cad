"""Suite de TORTURA de robustez (V6.1) — el contrato: nada tumba el documento.

Filosofía: PRIMERO estos tests (rojos), DESPUÉS los fixes que los ponen verdes. Tras
CUALQUIER fallo (excepción de un executor, .apolo corrupto, fuzzing de undo/redo,
autosave caído) el documento queda en un estado ÍNTEGRO Y VERIFICABLE — nunca a medias.

Los tests ACOTADOS (sin marca) corren en la suite normal (presupuesto ~30 s, primitivas
baratas). Los EXTENDIDOS (`@pytest.mark.torture`) se corren aparte: `pytest -m torture`.

Nota del ejecutor: varios tests referencian APIs que aún no existen cuando se escriben
(tolerant=, regen_suppressed, initialize_store, touch_definition). Es DELIBERADO: rojos
ahora, verdes tras las fases 2-3. Todo import de un símbolo nuevo va DENTRO del cuerpo
del test (nunca al top del módulo) para no tumbar la colección de la suite entera.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import random
import time
import zipfile

import pytest

from apolo.doc.document import Document, DocumentError

# ======================================================================= helpers


def _deep_doc_state(doc: Document) -> dict:
    """Estado PROFUNDO comparable del documento: todo lo que un rollback debe preservar
    byte-a-byte (menos las formas OCCT, que comparamos por volumen redondeado)."""
    return {
        "commands": copy.deepcopy(doc.commands),
        "scene": sorted((fid, round(f.shape.volume, 6)) for fid, f in doc.scene.items()),
        "joints": copy.deepcopy(doc.joints),
        "mates": copy.deepcopy(doc.mates),
        "constraints": copy.deepcopy(doc.constraints),
        "fasteners": copy.deepcopy(doc.fasteners),
        "grounds": copy.deepcopy(doc.grounds),
        "groups": copy.deepcopy(doc.groups),
        "regen_sigs": list(doc._regen_sigs),
        "ckpt_keys": sorted(doc._regen_ckpts),
        "seq": doc._seq,
    }


def _build_model(n: int) -> tuple[Document, list[str]]:
    """Modelo sintético con dims DISTINTAS por pieza (cajas + cilindros) + un par de
    juntas/fijadores/grupos + un pattern_group. Barato (primitivas)."""
    doc = Document("torture")
    ids: list[str] = []
    for i in range(n):
        if i % 2 == 0:
            cid = doc.execute("create_box", {
                "name": f"b{i}", "width": 40 + i, "depth": 30 + (i % 11),
                "height": 20 + (i % 7), "position": {"x": i * 120},
            })
        else:
            cid = doc.execute("create_cylinder", {
                "name": f"c{i}", "radius": 8 + (i % 5), "height": 25 + (i % 9),
                "position": {"x": i * 120, "y": 200},
            })
        ids.append(cid)
    if n >= 4:
        doc.execute("add_joint", {
            "name": "j1", "type": "giratoria", "parent": ids[0], "child": ids[1],
            "origin": {"x": 0, "y": 0, "z": 0}, "axis": {"x": 0, "y": 0, "z": 1},
            "lower": 0, "upper": 90,
        })
        doc.execute("fasten", {
            "name": "f1", "a": ids[2], "b": ids[3], "kind": "perno", "size": "M8", "qty": 4,
        })
        doc.execute("create_group", {"name": "G1", "members": [ids[0], ids[1]]})
    if n >= 6:
        doc.execute("pattern_group", {"source": ids[4], "count": 3, "spacing": {"y": 300}})
    return doc, ids


def _assert_replay_matches(mem: Document) -> None:
    """El replay desde el log (frío) reproduce EXACTO lo que hay en memoria."""
    fresh = Document.from_apolo_bytes(mem.to_apolo_bytes())
    assert sorted(fresh.scene) == sorted(mem.scene)
    for fid in mem.scene:
        assert abs(fresh.scene[fid].shape.volume - mem.scene[fid].shape.volume) < 1e-6
    assert set(fresh.joints) == set(mem.joints)
    assert {g: sorted(v["members"]) for g, v in fresh.groups.items()} == {
        g: sorted(v["members"]) for g, v in mem.groups.items()
    }


@contextlib.contextmanager
def _fault_on(cmd_type: str, predicate):
    """Envuelve el executor de `cmd_type`: en cada llamada evalúa predicate(n, args,
    kwargs); si devuelve True lanza CommandError en vez de ejecutar. Restaura al salir."""
    from apolo.commands.registry import REGISTRY, CommandError

    spec = REGISTRY[cmd_type]
    orig = spec.executor
    calls = {"n": 0}

    def wrapper(*args, **kwargs):
        calls["n"] += 1
        if predicate(calls["n"], args, kwargs):
            raise CommandError(f"fault inyectado en {cmd_type} (llamada {calls['n']})")
        return orig(*args, **kwargs)

    spec.executor = wrapper
    try:
        yield calls
    finally:
        spec.executor = orig


@contextlib.contextmanager
def _boom_resolve_all():
    """Hace fallar resolve_all a nivel del documento (POST-replay de variables). Simula
    variables circulares/inválidas SIEMPRE — para probar la atomicidad de regenerate."""
    from apolo.commands.expressions import ExpressionError
    from apolo.doc import document as docmod

    orig = docmod.resolve_all

    def boom(_vars):
        raise ExpressionError("resolve_all inyectado a fallar")

    docmod.resolve_all = boom
    try:
        yield
    finally:
        docmod.resolve_all = orig


def _rezip(base: bytes, *, manifest_edit=None, commands_edit=None,
           drop_attachments: bool = False) -> bytes:
    """Reempaqueta un .apolo aplicando ediciones a manifest.json/commands.json (o
    soltando attachments/). manifest_edit/commands_edit reciben el objeto parseado y
    devuelven el nuevo (o un str/ bytes crudo para inyectar basura)."""
    with zipfile.ZipFile(io.BytesIO(base)) as zf:
        names = zf.namelist()
        blobs = {n: zf.read(n) for n in names}
    manifest = json.loads(blobs["manifest.json"])
    commands = json.loads(blobs["commands.json"])
    if manifest_edit is not None:
        manifest = manifest_edit(manifest)
    if commands_edit is not None:
        commands = commands_edit(commands)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest if isinstance(manifest, (str, bytes))
                    else json.dumps(manifest, indent=2))
        zf.writestr("commands.json", commands if isinstance(commands, (str, bytes))
                    else json.dumps(commands, indent=2))
        if not drop_attachments:
            for n, b in blobs.items():
                if n.startswith("attachments/"):
                    zf.writestr(n, b)
    return out.getvalue()


# ============================================================ T1 — fuzz undo/redo


def test_T1_fuzz_undo_redo_keeps_integrity():
    """~120 ops pseudoaleatorias (execute/edit/undo/redo/remove) sobre ~40 primitivas.
    Tras CADA op el documento está íntegro; al final el replay-desde-log == memoria.
    Pin de oro: si sale rojo es un bug real de atomicidad, no un test frágil."""
    rng = random.Random(42)
    doc, ids = _build_model(40)
    for _ in range(120):
        op = rng.choice(["execute", "edit", "undo", "redo", "remove", "remove"])
        try:
            if op == "execute":
                doc.execute("create_box", {
                    "width": rng.randint(20, 80), "depth": rng.randint(20, 80),
                    "height": rng.randint(20, 80), "position": {"x": rng.randint(0, 6000)},
                })
            elif op == "edit":
                boxes = [c for c in doc.commands if c["type"] == "create_box"]
                if boxes:
                    c = rng.choice(boxes)
                    doc.edit(c["id"], {
                        "width": rng.randint(20, 90), "depth": rng.randint(20, 90),
                        "height": rng.randint(20, 90),
                    }, merge=True)
            elif op == "undo" and doc.can_undo:
                doc.undo()
            elif op == "redo" and doc.can_redo:
                doc.redo()
            elif op == "remove" and doc.commands:
                c = rng.choice(doc.commands)
                doc.remove_commands([c["id"]])
        except DocumentError:
            pass  # una op inválida (referencia colgando, etc.) es legítima: debe revertir
        assert doc.check_integrity() == []
    _assert_replay_matches(doc)


# ============================================ T2 — atomicidad de una mutación fallida


def test_T2_mutation_fault_is_atomic():
    """Un executor que revienta durante el replay de un edit → la mutación revierte por
    completo (estado profundo pre==post); quitado el fault, el reintento funciona."""
    doc, ids = _build_model(20)
    box = next(c["id"] for c in doc.commands if c["type"] == "create_box")
    before = _deep_doc_state(doc)
    # el fault revienta la PRIMERA llamada a create_box del replay (se consume una vez)
    with _fault_on("create_box", lambda n, a, k: n == 1):
        with pytest.raises(DocumentError):
            doc.edit(box, {"width": 123, "depth": 45, "height": 45}, merge=True)
    assert _deep_doc_state(doc) == before  # nada quedó a medias
    # sin fault, el mismo edit ahora entra
    doc.edit(box, {"width": 123, "depth": 45, "height": 45}, merge=True)
    assert doc.check_integrity() == []
    bb = doc.scene[box].shape.bounding_box()
    assert round(bb.max.X - bb.min.X) == 123


# ==================================== T3 — undo peek-then-commit (no pierde snapshot)


def test_T3_undo_survives_regenerate_failure():
    """Si la regeneración del undo revienta (resolve_all roto), o el undo completa o el
    doc queda EXACTO y el snapshot de deshacer NO se pierde (patrón peek-then-commit)."""
    doc, ids = _build_model(6)
    doc.execute("create_box", {"width": 33, "depth": 33, "height": 33, "position": {"x": 9000}})
    undo_len = len(doc._undo)
    assert undo_len >= 1
    before = _deep_doc_state(doc)
    with _boom_resolve_all():
        try:
            doc.undo()
        except DocumentError:
            pass
    assert len(doc._undo) == undo_len          # el snapshot NO se perdió
    assert _deep_doc_state(doc) == before       # doc EXACTO
    doc.undo()                                   # tras quitar el fault, el undo entra
    assert len(doc._undo) == undo_len - 1
    assert doc.check_integrity() == []


# ============================================ T4 — checkpoints corruptos no revientan


def test_T4_corrupt_checkpoints_never_crash():
    """Una caché de regeneración corrupta (valores basura, claves absurdas) NUNCA debe
    lanzar TypeError: regenera completo desde cero y queda íntegro."""
    doc, ids = _build_model(20)
    box = doc.commands[2]["id"]
    doc._regen_ckpts = {5: ("basura",), "x": (1, 2, 3), 999: 42}  # veneno
    doc.edit(box, {"width": 77, "depth": 40, "height": 40}, merge=True)  # no debe petar
    assert doc.check_integrity() == []
    assert _deep_doc_state(doc)["scene"] == _deep_doc_state(
        Document.from_apolo_bytes(doc.to_apolo_bytes())
    )["scene"]


# ============================================ T5 — regenerate atómico (escena vieja)


def test_T5_regenerate_is_atomic_on_resolve_failure():
    """Si resolve_all revienta POST-replay, regenerate NO debe dejar la escena nueva
    con las variables viejas: la escena entera queda como estaba (todo o nada)."""
    doc, ids = _build_model(10)
    box = next(c["id"] for c in doc.commands if c["type"] == "create_box")
    vol_old = doc.scene[box].shape.volume
    # cambiar el comando DIRECTAMENTE (sin _mutate) y regenerar bajo el fault
    for c in doc.commands:
        if c["id"] == box:
            c["params"] = {**c["params"], "width": 999, "depth": 999, "height": 999}
    with _boom_resolve_all():
        with pytest.raises(DocumentError):
            doc.regenerate()
    assert doc.scene[box].shape.volume == pytest.approx(vol_old, abs=1e-6)  # escena VIEJA


# ================================================ T6 — corruptor de .apolo (×5 modos)


def _healthy_bytes() -> bytes:
    doc, _ = _build_model(6)
    return doc.to_apolo_bytes()


def test_T6_truncated_zip_raises_clean():
    data = _healthy_bytes()
    with pytest.raises(DocumentError):
        Document.from_apolo_bytes(data[: len(data) // 2])


def test_T6_broken_commands_json_raises_clean():
    bad = _rezip(_healthy_bytes(), commands_edit=lambda _c: "{ esto no es json ]")
    with pytest.raises(DocumentError):
        Document.from_apolo_bytes(bad)


def test_T6_param_drift_raises_clean_strict():
    """Schema drift: un valor que HOY es inválido (p. ej. una cota <= 0 que en su día se
    coló) → la carga estricta NO abre en silencio, lanza DocumentError claro. (Una clave
    EXTRA desconocida no cuenta: pydantic la ignora a propósito, forward-compatible.)"""
    def poison(cmds):
        for c in cmds:
            if c["type"] == "create_box":
                c["params"]["width"] = -5  # fuera de rango bajo el schema de hoy
                break
        return cmds

    bad = _rezip(_healthy_bytes(), commands_edit=poison)
    with pytest.raises(DocumentError):
        Document.from_apolo_bytes(bad)  # estricto: un param inválido NO abre en silencio


def test_T6_missing_attachment_raises_clean():
    """Un insert_project cuyo attachment se soltó del ZIP → DocumentError claro."""
    host = Document("layout")
    donor, _ = _build_model(4)
    digest = host.add_attachment(donor.to_apolo_bytes())
    host.execute("insert_project", {"attachment": digest, "name": "M1"})
    bad = _rezip(host.to_apolo_bytes(), drop_attachments=True)
    with pytest.raises(DocumentError):
        Document.from_apolo_bytes(bad)


def test_T6_manifest_without_seq_no_id_collision():
    """Un log con removes deja max(c-id) > len(commands). Si el manifest pierde `seq`,
    el default no debe COLISIONAR ids al ejecutar después (guardia de seq)."""
    doc = Document("gaps")
    ids = [doc.execute("create_box", {"width": 30 + i}) for i in range(5)]  # c1..c5
    doc.remove_commands([ids[0], ids[1]])  # quedan c3,c4,c5 ; len=3 pero max=5
    stripped = _rezip(doc.to_apolo_bytes(),
                      manifest_edit=lambda m: {k: v for k, v in m.items() if k != "seq"})
    reopened = Document.from_apolo_bytes(stripped)
    reopened.execute("create_box", {"width": 999})  # NO debe reusar c4/c5
    all_ids = [c["id"] for c in reopened.commands]
    assert len(all_ids) == len(set(all_ids))  # sin colisión de ids


# ================================================ T7 — carga TOLERANTE (un comando roto)


def test_T7_tolerant_load_suppresses_bad_command():
    """`from_apolo_bytes(tolerant=True)` abre pese a un comando con param bogus: lo
    SUPRIME (reportado en regen_suppressed), el resto vive, y el LOG se conserva intacto."""
    doc, _ = _build_model(6)
    good = doc.to_apolo_bytes()

    def poison(cmds):
        # el ÚLTIMO cilindro (ids[5]) no es hijo de junta ni fijador: envenenarlo suprime
        # SOLO ese comando (envenenar uno con dependientes podaría además su junta)
        cyls = [c for c in cmds if c["type"] == "create_cylinder"]
        cyls[-1]["params"]["radius"] = -5  # inválido → CommandError en replay
        return cmds

    bad = _rezip(good, commands_edit=poison)
    d = Document.from_apolo_bytes(bad, tolerant=True)
    assert len(d.regen_suppressed) == 1
    entry = d.regen_suppressed[0]
    assert set(entry) >= {"command_id", "type", "error"} and entry["type"] == "create_cylinder"
    assert len(d.scene) >= 1  # el resto de las piezas viven
    # el log NO se toca: al reguardar, el comando envenenado sigue ahí intacto
    with zipfile.ZipFile(io.BytesIO(d.to_apolo_bytes())) as zf:
        saved = json.loads(zf.read("commands.json"))
    assert any(c["params"].get("radius") == -5 for c in saved)


def test_T7_tolerant_equals_strict_on_healthy_project():
    """En un proyecto SANO, la carga tolerante y la estricta son byte-idénticas
    (el modo tolerante no debe enmascarar ni alterar nada del camino feliz)."""
    good = _healthy_bytes()
    strict = Document.from_apolo_bytes(good)
    tol = Document.from_apolo_bytes(good, tolerant=True)
    assert tol.regen_suppressed == []
    assert strict.to_apolo_bytes() == tol.to_apolo_bytes()


# NOTA: la tortura de la CAPA API (T8 DEFINITIONS/LRU, T9 insert_project precheck,
# T10 autosave, T11 startup, T12 project/new, T13 WS, T14 health) y los tests EXTENDIDOS
# (@pytest.mark.torture) llegan con sus fixes en el commit V6.1b.
