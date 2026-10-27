"""Mixin de PERSISTENCIA del documento: el `.apolo` (ZIP: manifest + commands + adjuntos) y
la siembra del open caliente desde la caché de geometría (`_try_warm`).

Sale de `document.py` (plan partir-nucleo-congelado, F5): `Document` hereda los métodos tal cual;
`from_apolo_bytes`/`load` construyen `cls(...)`, o sea un `Document`.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from apolo.commands.state import RegenState
from apolo.doc import carril, ext_manifest, solo_lectura, variantes
from apolo.doc.errors import DocumentError

if TYPE_CHECKING:
    from apolo.doc.document import Document

FORMAT_VERSION = 2  # v2 añade attachments/ (archivos STEP importados); abre v1 sin cambios

# id de comando c-numérico (para la guardia de seq y check_integrity)
_CID_RE = re.compile(r"^c(\d+)$")


class PersistenciaDocumento:
    def _try_warm(self, warm) -> None:
        """Siembra la caché de regeneración desde un blob de geomcache YA deserializado
        (V6.2a): ``warm = (cached_sigs, state: RegenState, definitions)``. Si ``cached_sigs`` es
        PREFIJO (o igual) de las firmas del log cargado, re-registra las definiciones
        canónicas y siembra ``_regen_sigs``/``_regen_ckpts`` con el estado del último
        comando cacheado → el siguiente ``regenerate()`` reanuda de ese checkpoint (replay
        de solo la cola). NUNCA lanza: ante cualquier duda deja el doc virgen (replay
        completo). El caller valida integridad tras regenerar y descarta si algo huele mal."""
        try:
            cached_sigs, state, definitions = warm
        except Exception:
            return
        if not cached_sigs or not isinstance(cached_sigs, list) or not isinstance(state, RegenState):
            return
        sigs = carril.firmas(*carril.separar(self.commands)[:2])  # las del log realmente cargado
        # las firmas cacheadas deben ser PREFIJO (o iguales) de las del log (el log pudo
        # crecer desde la última caché; si en cambio DIVERGE o es más largo → descartar)
        n = len(cached_sigs)
        if n > len(sigs) or sigs[:n] != list(cached_sigs):
            return
        # re-registrar las definiciones canónicas: sin esto los mesh_key de la escena
        # restaurada cuelgan (instancing perdido → payload explota; check_integrity lo
        # marcaría 'degradado'). El camino feliz NO debe caer ahí.
        try:
            from apolo.commands.registry import register_definition

            for key, shape in definitions.items():
                register_definition(key, shape)
        except Exception:
            return
        # sembrar: el estado del último comando cacheado como checkpoint en n-1
        self._regen_sigs = list(cached_sigs)
        self._regen_ckpts = {n - 1: state}

    # --------------------------------------------------------- persistencia
    def to_apolo_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "app": "genix-apolo-cad",
                        "version": FORMAT_VERSION,
                        "name": self.name,
                        "units": "mm",
                        "hidden": sorted(self.hidden),
                        "seq": self._seq,
                        "configurations": self.configurations,
                        "configurations_format": variantes.FORMATO,  # tabla de columnas
                        "colors": self.colors,
                        "materials": self.materials,
                        "sketch_guides": sorted(self.sketch_guides),
                        "vertical": self.vertical,
                        "motion": self.motion,
                        "requirements": self.requirements,
                        **({"comercial": self.comercial} if self.comercial else {}),
                        "fea": self.fea,
                        "stackups": self.stackups,
                        "escenarios": self.escenarios, **({"tensores": self.tensores} if self.tensores else {}), **({"funciones": self.funciones} if self.funciones else {}), **({"justificadas": self.justificadas} if self.justificadas else {}), **({"puerta_primera": self.puerta_primera} if self.puerta_primera else {}), **ext_manifest.al_manifest(self),
                        "agent_notes": self.agent_notes,
                    },
                    indent=2,
                ),
            )
            zf.writestr("commands.json", json.dumps(self.commands, indent=2))
            for digest, data in self.attachments.items():
                zf.writestr(f"attachments/{digest}.bin", data)
        return buf.getvalue()

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_apolo_bytes())

    @classmethod
    def from_apolo_bytes(
        cls, data: bytes, *, regenerate: bool = True, tolerant: bool = False, warm=None
    ) -> "Document":
        """Con ``regenerate=False`` devuelve el documento SIN reproducir el log —
        para editarlo antes del primer replay (sandbox de insert_project). Con
        ``tolerant=True`` (SOLO en rutas de CARGA: arranque, open, restore) un comando
        que revienta se SUPRIME en vez de abortar la apertura — reportado en
        ``regen_suppressed``, con el LOG intacto. Las mutaciones cargan estrictas.

        ``warm`` (V6.2a): tupla de geomcache YA deserializada ``(sigs, state,
        definitions)`` que evita el replay del log si sus firmas son prefijo del log
        cargado (open caliente). Cinturón y tirantes: tras regenerar de la caché se
        verifica la integridad y, si hay violaciones NO-degradadas, se descarta la caché
        y se replaya en frío. La caché NUNCA es autoritativa (el .apolo lo es)."""
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                commands = json.loads(zf.read("commands.json"))
                attachments = {
                    Path(name).stem: zf.read(name)
                    for name in zf.namelist()
                    if name.startswith("attachments/")
                }
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
            raise DocumentError(f"Archivo .apolo inválido: {exc}") from exc
        if manifest.get("version", 0) > FORMAT_VERSION:
            raise DocumentError("El archivo fue creado con una versión más reciente de Apolo")
        doc = cls(manifest.get("name", "Sin título"))
        doc.commands = commands
        doc.hidden = set(manifest.get("hidden", []))
        doc.attachments = attachments
        doc.configurations = variantes.cargar(manifest, commands)  # sin bandera: migra fotos
        doc.colors = manifest.get("colors", {})
        doc.materials = manifest.get("materials", {})
        # sketch_guides (command_ids) poda las huérfanas de cirugías SOLO en la carga: el metadato
        # no viaja en los snapshots de undo y podarlo al mutar lo perdería al deshacer. Criterio de
        # _cmd_alive: id del log o sintético '{cmd}_{orig}' de insert_project con prefijo vivo.
        _log_ids = {c["id"] for c in commands}
        doc.sketch_guides = {
            cid
            for cid in manifest.get("sketch_guides", [])
            if cid in _log_ids or cid.split("_", 1)[0] in _log_ids
        }
        doc.vertical = manifest.get("vertical", "metalmecanica")
        _m = manifest.get("motion", {})
        # migración: proyectos viejos guardaban el motion como UNA lista de fotogramas
        doc.motion = ({"Estudio 1": _m} if _m else {}) if isinstance(_m, list) else dict(_m)
        doc.requirements = manifest.get("requirements", {})
        _c = manifest.get("comercial")  # sin el campo (un .apolo viejo): sin identificación
        doc.comercial = dict(_c) if isinstance(_c, dict) else {}
        doc.fea = manifest.get("fea", {})
        doc.stackups = manifest.get("stackups", {})  # cadenas de cotas (V7.3)
        doc.escenarios = manifest.get("escenarios", {})  # pruebas de la máquina (V8.3 D12)
        doc.tensores, doc.funciones, doc.agent_notes = (manifest.get(k, []) for k in ("tensores", "funciones", "agent_notes"))
        doc.justificadas = list(manifest.get("justificadas") or [])  # puerta-sin-sobrediseno D11
        doc.puerta_primera = dict(manifest.get("puerta_primera") or {})  # D9: sin él, nada «agregado»
        doc.ext = ext_manifest.de_manifest(manifest)  # la de toda extensión, instalada o no (F1d)
        # guardia de seq: el próximo cmd_id nunca debe colisionar con uno del log aunque
        # el manifest venga sin `seq` o con un `seq` menor que el mayor c-id vivo (un log
        # con removes deja huecos: len(commands) < max(sufijo)).
        max_suffix = 0
        for c in commands:
            mo = _CID_RE.match(str(c.get("id", "")))
            if mo:
                max_suffix = max(max_suffix, int(mo.group(1)))
        doc._seq = max(int(manifest.get("seq", 0) or 0), len(commands), max_suffix)
        if regenerate:
            tolerant = solo_lectura.marcar(doc) or tolerant  # D4: con extensión ausente, ver sí
            if warm is not None:
                doc._try_warm(warm)  # siembra la caché de regen si la firma es prefijo
                # cinturón y tirantes: el regenerate SEMBRADO no debe (a) LANZAR ni (b) dejar
                # violaciones no-degradadas → descartar la caché y replay FRÍO. (a) cubre una excepción
                # de OCCT en la cola / un DocumentError de resolve_all / un ckpt corrupto (V6.2e Fix 5).
                cold_needed = False
                try:
                    doc.regenerate(tolerant=tolerant)
                except Exception:  # noqa: BLE001 — el regenerate con la caché sembrada reventó
                    cold_needed = True
                else:
                    cold_needed = any(
                        not i.startswith("degradado") for i in doc.check_integrity()
                    )
                if cold_needed:
                    doc._regen_sigs, doc._regen_ckpts = [], {}
                    doc.regenerate(tolerant=tolerant)  # frío: si ESTE lanza, el doc sí está roto
            else:
                doc.regenerate(tolerant=tolerant)
        return doc

    @classmethod
    def load(cls, path: str | Path) -> "Document":
        return cls.from_apolo_bytes(Path(path).read_bytes())
