"""Versión por comando: cambiar UN executor invalida la caché SÓLO de quien lo usa (F5: D9).

Plan `estado-regen-y-params-estrictos`. La firma de un comando era sha1(previa + id + params):
nada del código. Un cambio en UN executor obligaba a subir `GEOM_CACHE_EPOCH`, que invalida
TODOS los proyectos. Hoy `CommandSpec.version` entra a la firma SÓLO si es ≠ 1 (con todo en
v1 la firma es byte-idéntica a la histórica: el golden de los 122 documentos lo verifica) y un
comando COMPUESTO (`insert_project`, que reproduce otros executors) lleva el resumen de TODAS
las versiones ≠ 1 del registro.
"""

from __future__ import annotations

import hashlib
import json

import pytest

import apolo.doc.document as docmod
from apolo.commands.models import CreateBoxParams
from apolo.commands.registry import REGISTRY
from apolo.commands.spec import CommandSpec, version_tag
from apolo.doc.document import Document, _cmd_sig
from apolo.doc.geomcache import pack, unpack


def _firmas(doc: Document) -> list[str]:
    out, prev = [], ""
    for cmd in doc.commands:
        prev = _cmd_sig(prev, cmd)
        out.append(prev)
    return out


def _con_cilindro() -> Document:
    doc = Document("con-cilindro")
    doc.execute("set_variable", {"name": "W", "expression": "40"})
    doc.execute("create_box", {"name": "A", "width": "=W"})
    doc.execute("create_box", {"name": "B", "position": {"x": 200}})
    doc.execute("create_cylinder", {"name": "C", "radius": 20, "position": {"x": 400}})
    doc.execute("create_box", {"name": "D", "position": {"x": 600}})
    return doc


def _sin_cilindro() -> Document:
    doc = Document("sin-cilindro")
    doc.execute("create_box", {"name": "A"})
    doc.execute("create_box", {"name": "B", "position": {"x": 200}})
    return doc


def _replays(doc_bytes: bytes, warm) -> tuple[Document, int]:
    calls = {"n": 0}
    orig = docmod.execute_command

    def spy(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    docmod.execute_command = spy
    try:
        doc = Document.from_apolo_bytes(doc_bytes, warm=warm)
    finally:
        docmod.execute_command = orig
    return doc, calls["n"]


def test_en_v1_la_firma_es_la_historica():
    """sha1(previa + id + params) sin nada más: con todo en v1 las cachés y el golden no se
    enteran de que existe la versión."""
    cmd = {"id": "c7", "type": "create_box", "params": {"width": 10, "name": "x"}}
    h = hashlib.sha1(b"previa")
    h.update(b"c7")
    h.update(json.dumps(cmd["params"], sort_keys=True, default=str).encode())
    assert REGISTRY["create_box"].version == 1
    assert version_tag(REGISTRY, "create_box") == ""
    assert _cmd_sig("previa", cmd) == h.hexdigest()


def test_subir_la_version_cambia_las_firmas_desde_su_primer_comando(monkeypatch):
    doc = _con_cilindro()
    antes = _firmas(doc)
    i = next(k for k, c in enumerate(doc.commands) if c["type"] == "create_cylinder")
    monkeypatch.setattr(REGISTRY["create_cylinder"], "version", 2)
    despues = _firmas(doc)
    assert despues[:i] == antes[:i]  # lo anterior al cilindro sigue valiendo
    assert all(a != b for a, b in zip(antes[i:], despues[i:]))  # y desde él, todo cambia


def test_un_proyecto_que_no_lo_usa_no_se_entera(monkeypatch):
    doc = _sin_cilindro()
    antes = _firmas(doc)
    monkeypatch.setattr(REGISTRY["create_cylinder"], "version", 2)
    assert _firmas(doc) == antes


def test_insert_project_cambia_con_cualquier_version(monkeypatch):
    ins = {"id": "c1", "type": "insert_project", "params": {"name": "L", "attachment": "ab"}}
    box = {"id": "c2", "type": "create_box", "params": {}}
    assert REGISTRY["insert_project"].composite
    antes_ins, antes_box = _cmd_sig("", ins), _cmd_sig("", box)
    monkeypatch.setattr(REGISTRY["fillet"], "version", 3)
    assert _cmd_sig("", ins) != antes_ins  # reproduce executors que sus params no nombran
    assert _cmd_sig("", box) == antes_box
    assert version_tag(REGISTRY, "insert_project") == "|v:fillet@3"


def test_un_blob_de_la_version_anterior_se_descarta_en_el_open(monkeypatch):
    con, sin = _con_cilindro(), _sin_cilindro()
    datos_con, warm_con = con.to_apolo_bytes(), unpack(pack(con))
    datos_sin, warm_sin = sin.to_apolo_bytes(), unpack(pack(sin))
    assert warm_con is not None and warm_sin is not None
    monkeypatch.setattr(REGISTRY["create_cylinder"], "version", 2)

    frio, n = _replays(datos_con, warm_con)
    assert n == len(con.commands)  # las firmas cacheadas ya no son prefijo → replay frío
    assert sorted(frio.scene) == sorted(con.scene) and frio.check_integrity() == []
    _, n = _replays(datos_sin, warm_sin)
    assert n == 0  # el proyecto sin cilindros sigue abriendo caliente


@pytest.mark.parametrize("version", [0, -1, True, 1.5, "2"])
def test_la_version_se_valida_al_registrar(version):
    with pytest.raises(ValueError, match="version"):
        CommandSpec("x", "X", "crear", CreateBoxParams, lambda ctx, cmd_id, p: None,
                    version=version)


def test_defaults_de_un_comando_nuevo():
    spec = CommandSpec("x", "X", "crear", CreateBoxParams, lambda ctx, cmd_id, p: None)
    assert spec.version == 1 and spec.composite is False
    assert [t for t, s in REGISTRY.items() if s.composite] == ["insert_project"]
