"""Almacén de proyectos en SQLite (multiproyecto + autoguardado + revisiones).

Cada proyecto guarda los bytes .apolo completos (el documento ES el log de
comandos, así que pesa KBs, no MBs: autoguardar en cada mutación es barato).
Las revisiones son instantáneas manuales con nota, restaurables.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from apolo.doc import Document


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ProjectStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    pieces INTEGER DEFAULT 0,
                    data BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    pieces INTEGER DEFAULT 0,
                    data BLOB NOT NULL
                );
                """
            )

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA foreign_keys = ON")
        return con

    # ------------------------------------------------------------- proyectos
    def list_projects(self) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT id, name, updated_at, pieces FROM projects ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {"id": r[0], "name": r[1], "updated_at": r[2], "pieces": r[3]} for r in rows
        ]

    def create(self, doc: Document) -> int:
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO projects(name, updated_at, pieces, data) VALUES(?,?,?,?)",
                (doc.name, _now(), len(doc.scene), doc.to_apolo_bytes()),
            )
            return int(cur.lastrowid)

    def save(self, project_id: int, doc: Document) -> None:
        with self._conn() as con:
            con.execute(
                "UPDATE projects SET name=?, updated_at=?, pieces=?, data=? WHERE id=?",
                (doc.name, _now(), len(doc.scene), doc.to_apolo_bytes(), project_id),
            )

    def load(self, project_id: int) -> Document:
        with self._conn() as con:
            row = con.execute("SELECT data FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"No existe el proyecto {project_id}")
        return Document.from_apolo_bytes(row[0])

    def delete(self, project_id: int) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM projects WHERE id=?", (project_id,))

    def duplicate(self, project_id: int, new_name: str | None = None) -> int:
        doc = self.load(project_id)
        doc.name = new_name or f"{doc.name} (copia)"
        return self.create(doc)

    def most_recent_id(self) -> int | None:
        with self._conn() as con:
            row = con.execute("SELECT id FROM projects ORDER BY updated_at DESC LIMIT 1").fetchone()
        return int(row[0]) if row else None

    # ------------------------------------------------------------ revisiones
    def save_revision(self, project_id: int, doc: Document, note: str) -> int:
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO revisions(project_id, note, created_at, pieces, data) VALUES(?,?,?,?,?)",
                (project_id, note or "Sin nota", _now(), len(doc.scene), doc.to_apolo_bytes()),
            )
            return int(cur.lastrowid)

    def list_revisions(self, project_id: int) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT id, note, created_at, pieces FROM revisions WHERE project_id=? ORDER BY id DESC",
                (project_id,),
            ).fetchall()
        return [
            {"id": r[0], "note": r[1], "created_at": r[2], "pieces": r[3]} for r in rows
        ]

    def load_revision(self, revision_id: int) -> tuple[int, Document]:
        with self._conn() as con:
            row = con.execute(
                "SELECT project_id, data FROM revisions WHERE id=?", (revision_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"No existe la revisión {revision_id}")
        return int(row[0]), Document.from_apolo_bytes(row[1])
