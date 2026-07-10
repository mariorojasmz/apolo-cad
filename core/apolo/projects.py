"""Almacén de proyectos en SQLite (multiproyecto + autoguardado + revisiones).

Cada proyecto guarda los bytes .apolo completos (el documento ES el log de
comandos, así que pesa KBs, no MBs: autoguardar en cada mutación es barato).
Las revisiones son instantáneas manuales con nota, restaurables.
"""

from __future__ import annotations

import os
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
                -- Caché de geometría por firma (V6.2a): estado regenerado + definiciones
                -- canónicas para el OPEN CALIENTE. LOCAL, nunca dentro del .apolo (pickle
                -- de origen propio). `sig` = última firma del log (saber si está al día sin
                -- deserializar). Cascada al borrar el proyecto. Perderla solo cuesta replay.
                CREATE TABLE IF NOT EXISTS geom_cache(
                    project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                    sig TEXT NOT NULL,
                    data BLOB NOT NULL,
                    updated_at TEXT NOT NULL
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

    def save_raw(self, project_id: int, name: str, pieces: int, data: bytes) -> None:
        """Guarda BYTES ya serializados (V6.2d): el flush con debounce toma
        ``to_apolo_bytes()`` bajo STATE_LOCK y escribe aquí FUERA del lock."""
        with self._conn() as con:
            con.execute(
                "UPDATE projects SET name=?, updated_at=?, pieces=?, data=? WHERE id=?",
                (name, _now(), pieces, data, project_id),
            )

    def load_bytes(self, project_id: int) -> bytes:
        """Bytes .apolo crudos (sin regenerar) — snapshot para insert_project."""
        with self._conn() as con:
            row = con.execute("SELECT data FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"No existe el proyecto {project_id}")
        return row[0]

    def load(self, project_id: int, *, tolerant: bool = False) -> Document:
        """Carga un proyecto. ``tolerant=True`` (rutas de apertura) suprime comandos
        rotos en vez de negar la apertura (schema drift) — ver Document.regenerate.
        Open CALIENTE (V6.2a): si hay caché de geometría al día, se pasa como ``warm=`` a
        ``from_apolo_bytes`` para reanudar del checkpoint en vez de replayar (kill-switch
        ``APOLO_GEOM_CACHE=0``). La caché nunca es autoritativa: el .apolo lo es.
        V6.2e Fix 6: si NO hubo warm-hit útil o la caché estaba de una firma vieja, se PUEBLA
        aquí (pack+save, ~40 ms) — un proyecto que solo se ABRE jamás la poblaría vía el flush
        post-mutación y abriría frío para siempre (agravado por bumps de epoch del formato)."""
        cache_on = os.environ.get("APOLO_GEOM_CACHE") != "0"
        warm = None
        cached_sig = None
        if cache_on:
            try:  # V6.2e: una página corrupta de geom_cache no debe tumbar el open del .apolo sano
                row = self.load_geom_cache(project_id)
            except Exception:
                row = None
            if row is not None:
                from apolo.doc.geomcache import unpack

                cached_sig = row[0]
                warm = unpack(row[1])
        doc = Document.from_apolo_bytes(
            self.load_bytes(project_id), tolerant=tolerant, warm=warm
        )
        if cache_on:
            sig = doc._regen_sigs[-1] if doc._regen_sigs else None
            if sig is not None and (warm is None or cached_sig != sig):
                try:
                    from apolo.doc.geomcache import pack

                    blob = pack(doc)
                    if blob is not None:
                        self.save_geom_cache(project_id, sig, blob)
                except Exception:  # best-effort: perder la caché solo cuesta un replay
                    pass
        return doc

    # -------------------------------------------------------- caché de geometría
    def save_geom_cache(self, project_id: int, sig: str, blob: bytes) -> None:
        """Persiste (o reemplaza) la caché de geometría de un proyecto. INSERT OR REPLACE
        respeta la FK a projects (solo se cachea un proyecto existente)."""
        with self._conn() as con:
            con.execute(
                "INSERT OR REPLACE INTO geom_cache(project_id, sig, data, updated_at) "
                "VALUES(?,?,?,?)",
                (project_id, sig, blob, _now()),
            )

    def geom_cache_sig(self, project_id: int) -> str | None:
        """Solo la firma cacheada (sin deserializar el blob) — guard barato de escritura:
        no re-empacar si la geometría no cambió respecto a lo ya persistido."""
        with self._conn() as con:
            row = con.execute(
                "SELECT sig FROM geom_cache WHERE project_id=?", (project_id,)
            ).fetchone()
        return row[0] if row else None

    def load_geom_cache(self, project_id: int) -> tuple[str, bytes] | None:
        """(sig, blob) de la caché de geometría, o None si no hay."""
        with self._conn() as con:
            row = con.execute(
                "SELECT sig, data FROM geom_cache WHERE project_id=?", (project_id,)
            ).fetchone()
        return (row[0], row[1]) if row else None

    def delete_geom_cache(self, project_id: int) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM geom_cache WHERE project_id=?", (project_id,))

    def delete(self, project_id: int) -> None:
        # geom_cache cascada por la FK; revisions también (ON DELETE CASCADE + PRAGMA)
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

    def load_revision(self, revision_id: int, *, tolerant: bool = False) -> tuple[int, Document]:
        with self._conn() as con:
            row = con.execute(
                "SELECT project_id, data FROM revisions WHERE id=?", (revision_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"No existe la revisión {revision_id}")
        return int(row[0]), Document.from_apolo_bytes(row[1], tolerant=tolerant)
