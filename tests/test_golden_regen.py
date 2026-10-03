"""El golden de regeneración (`scripts/golden_regen.py`) ve las diferencias y sólo ellas.

Es el gate de cada fase del plan `estado-regen-y-params-estrictos` (D1): si diera falso verde,
un refactor del regenerate podría cambiar la geometría de los proyectos guardados sin que
nadie se entere; si diera falso rojo, nadie le creería. Se prueba con dos documentos en una
SQLite de `tmp_path`: misma base → sin diferencias; un param cambiado → la diferencia sale y
nombra el documento y el campo.
"""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest

from apolo.doc.document import Document
from apolo.projects import ProjectStore

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def golden():
    spec = importlib.util.spec_from_file_location("golden_regen", RAIZ / "scripts" / "golden_regen.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _doc_a() -> Document:
    d = Document("A")
    d.execute("set_variable", {"name": "W", "expression": "60"})
    a = d.execute("create_box", {"name": "Base", "width": "=W", "depth": 40, "height": 20})
    b = d.execute("create_cylinder", {"name": "Eje", "radius": 8, "height": 50,
                                      "position": {"x": 100}})
    d.execute("add_joint", {"name": "j1", "type": "giratoria", "parent": a, "child": b,
                            "origin": {"x": 100, "y": 0, "z": 0}, "axis": {"x": 0, "y": 0, "z": 1}})
    d.execute("create_group", {"name": "G", "members": [a, b]})
    return d


def _doc_b() -> Document:
    d = Document("B")
    s = d.execute("create_box", {"name": "Listón", "width": 30, "depth": 30, "height": 10})
    # clave desconocida a propósito: pattern_linear no tiene `name` (se ignora en el replay)
    d.execute("pattern_linear", {"feature": s, "count": 3, "spacing": {"x": 50}, "name": "copias"})
    return d


def _db(path: Path) -> Path:
    store = ProjectStore(str(path))
    pid = store.create(_doc_a())
    store.create(_doc_b())
    store.save_revision(pid, _doc_a(), "rev 1")
    return path


def _set_param(db: Path, project_id: int, cmd_index: int, key: str, value) -> None:
    """Reescribe un param del log guardado (directo en la SQLite de prueba)."""
    with sqlite3.connect(db) as con:
        data = con.execute("SELECT data FROM projects WHERE id=?", (project_id,)).fetchone()[0]
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            files = {n: zf.read(n) for n in zf.namelist()}
        cmds = json.loads(files["commands.json"])
        cmds[cmd_index]["params"][key] = value
        files["commands.json"] = json.dumps(cmds).encode()
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zf:
            for n, b in files.items():
                zf.writestr(n, b)
        con.execute("UPDATE projects SET data=? WHERE id=?", (out.getvalue(), project_id))


def test_misma_base_sin_diferencias(golden, tmp_path):
    db = _db(tmp_path / "a.db")
    g1 = golden.build_golden(db, revisions=True, log=lambda *_: None)
    g2 = golden.build_golden(db, revisions=True, log=lambda *_: None)
    assert sorted(g1["docs"]) == ["proyecto:1", "proyecto:2", "revision:1"]
    assert golden.compare(g1, g2) == []
    fp = g1["docs"]["proyecto:1"]
    assert set(fp["features"]) == {"c2", "c3"} and fp["joints"]["j1"]["child"] == "c3"
    assert fp["groups"]["G"]["members"] == ["c2", "c3"]
    assert fp["variables"] == {"W": 60.0} and fp["last_sig"] and fp["integrity"] == []
    assert fp["features"]["c2"]["volume"] == pytest.approx(60 * 40 * 20)
    # el JSON escrito y releído compara igual (lo que hace --compare entre dos corridas)
    again = json.loads(json.dumps(g1, sort_keys=True))
    assert golden.compare(g1, again) == []


def test_un_param_cambiado_sale_en_el_diff(golden, tmp_path):
    db = _db(tmp_path / "a.db")
    base = golden.build_golden(db, revisions=True, log=lambda *_: None)
    otra = tmp_path / "b.db"
    shutil.copy(db, otra)
    _set_param(otra, 2, 0, "width", 31)  # el listón del proyecto 2: 30 → 31
    nuevo = golden.build_golden(otra, revisions=True, log=lambda *_: None)
    diffs = golden.compare(base, nuevo)
    texto = "\n".join(diffs)
    assert diffs and "proyecto:2" in texto
    assert "proyecto:1" not in texto and "revision:1" not in texto
    assert "volume" in texto and "last_sig" in texto  # la geometría y la firma cambiaron
    # el CLI devuelve código ≠ 0 cuando difiere y 0 cuando no
    pa, pb = tmp_path / "a.json", tmp_path / "b.json"
    pa.write_text(json.dumps(base), encoding="utf-8")
    pb.write_text(json.dumps(nuevo), encoding="utf-8")
    assert golden.main(["--compare", str(pa), str(pb)]) == 1
    assert golden.main(["--compare", str(pa), str(pa)]) == 0


def test_freeze_copia_sin_tocar_el_origen(golden, tmp_path):
    db = _db(tmp_path / "origen.db")
    antes = db.read_bytes()
    info = golden.freeze(db, tmp_path / "congelada")
    assert db.read_bytes() == antes
    assert (info["proyectos"], info["revisiones"]) == (2, 1)
    g1 = golden.build_golden(db, revisions=True, log=lambda *_: None)
    g2 = golden.build_golden(info["copia"], revisions=True, log=lambda *_: None)
    assert golden.compare(g1, g2) == []
    with pytest.raises(SystemExit):
        golden.freeze(db, db)  # jamás sobre el origen


def test_scan_keys_encuentra_la_clave_desconocida(golden, tmp_path):
    acc = golden.scan_keys(_db(tmp_path / "a.db"), revisions=True)
    assert acc["claves"]["pattern_linear.name"]["veces"] == 1
    assert acc["proyectos"]["con_claves"] == 1 and acc["revisiones"]["con_claves"] == 0
    assert acc["proyectos"]["otras"] == 0 and acc["proyectos"]["tipos"] == 0
