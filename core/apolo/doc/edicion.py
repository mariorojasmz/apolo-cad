"""Mixin de EDICIÓN del documento: ejecutar, editar y borrar comandos del log, y adjuntos.

Sale de `document.py` (plan partir-nucleo-congelado, F5): `Document` hereda los métodos tal cual
(mismo nombre y texto). Usan lo que `Document` define (`_mutate`, `_append_record`, `_snapshot`,
`_restore`, `regenerate`, `_check_strict`, `_push_undo`): el mixin no se usa solo.
"""

from __future__ import annotations

import hashlib

from apolo.commands.registry import REGISTRY, validate_params
from apolo.commands.strict import reject_unknown
from apolo.doc import carril, sello
from apolo.doc.errors import ContractError, DocumentError


class EdicionDocumento:
    def execute(self, cmd_type: str, params: dict) -> str:
        validate_params(cmd_type, params, self.variables_raw, strict=True)
        holder: dict[str, str] = {}

        def apply():
            holder["id"] = self._append_record(cmd_type, params)

        self._mutate(apply)
        return holder["id"]

    def execute_many(self, actions: list[dict], verify=None) -> list[str]:
        """Lote ATÓMICO: UN regenerate y UN paso de undo; '$k' (1-based) = cmd_id de la
        k-ésima acción. Una clave que el comando no declara rechaza el lote ANTES de tocar
        nada (entrada estricta: sólo mira claves, no valores). Los valores NO se pre-validan:
        el regenerate final valida en orden con las variables en construcción (set_variable
        + su uso en el mismo lote); si él o '$k' fallan, revierte TODO el lote.

        `verify` (V6.5b) = contrato opcional ``(scene, created) -> results`` tras el
        regenerate; una aserción falsa revierte todo y lanza ContractError. Corre DENTRO del
        try: el snapshot se CONSUME sin entrada de undo fantasma."""
        from apolo.batch import resolve_refs  # perezoso: evita ciclo document<->batch

        if not actions:
            return []
        for action in actions:
            reject_unknown(REGISTRY.get(action.get("type")), action.get("params") or {})
        snap, escena = self._snapshot(), self.scene
        created: list[str | None] = []
        try:
            for action in actions:
                params = resolve_refs(action.get("params") or {}, created)
                created.append(self._append_record(action["type"], params))
            self.regenerate()
            self._check_strict()
            if verify is not None:
                results = verify(self.scene, [c for c in created if c is not None])
                if any(not r.get("ok") for r in results):
                    raise ContractError(results)
        except Exception:
            self._restore(snap)
            raise
        self._push_undo(snap, escena)
        return [c for c in created if c is not None]

    def edit_many(self, edits: list[dict], merge: bool = False, verify=None) -> list[str]:
        """Edita VARIOS comandos en UN lote atómico: un solo regenerate y un solo paso de undo.
        edits = [{"command_id": "...", "params": {...}}, ...]. Como execute_many, sólo las claves
        son estrictas (una NUEVA que el comando no declara revierte el lote; una guardada pasa) y
        los valores los valida el regenerate final. merge=True: PATCH superficial, como edit.

        `verify` (V6.5b) = contrato del lote, igual que en execute_many (recibe los
        command_ids TOCADOS como `created` → `$k` referencia el k-ésimo editado)."""
        if not edits:
            return []
        snap, escena = self._snapshot(), self.scene
        touched: list[str] = []
        try:
            for e in edits:
                cid = e["command_id"]
                cmd = next((c for c in self.commands if c["id"] == cid), None)
                if cmd is None:
                    raise DocumentError(f"No existe el comando '{cid}'")
                params = e.get("params") or {}
                if merge:
                    params = {**cmd["params"], **params}
                reject_unknown(REGISTRY.get(cmd["type"]), params, previous=cmd["params"])
                params = sello.al_editar(cmd["type"], params, cmd["params"])
                cmd["params"] = carril.materializar(self.commands, cmd["type"], params, cid)
                touched.append(cid)
            self.regenerate()
            self._check_strict()
            if verify is not None:
                results = verify(self.scene, touched)
                if any(not r.get("ok") for r in results):
                    raise ContractError(results)
        except Exception:
            self._restore(snap)
            raise
        self._push_undo(snap, escena)
        return touched

    def edit(
        self, command_id: str, params: dict, coalesce: bool = False, merge: bool = False
    ) -> str:
        """Edita los params de un comando: REEMPLAZA (lo omitido vuelve a su default) o, con
        `merge=True`, PATCH superficial (un sub-objeto se reemplaza entero). Estricta: rechaza
        una clave NUEVA que el comando no declara (una ya guardada pasa); luego, `al_editar`."""
        cmd = next((c for c in self.commands if c["id"] == command_id), None)
        if cmd is None:
            raise DocumentError(f"No existe el comando '{command_id}'")
        if merge:
            params = {**cmd["params"], **params}
        validate_params(cmd["type"], params, self.variables_raw, strict=True,
                        previous=cmd["params"])
        params = sello.al_editar(cmd["type"], params, cmd["params"])

        def apply():
            cmd["params"] = carril.materializar(self.commands, cmd["type"], params, command_id)

        self._mutate(apply, f"edit:{command_id}" if coalesce else None, foco=command_id)
        return command_id

    def remove_commands(self, command_ids: list[str], ediciones: dict | None = None) -> None:
        """Elimina comandos del log y regenera; revierte si algo queda roto. `ediciones` {id:
        params} REEMPLAZA los de otros comandos en el MISMO cambio (1 undo; plan cirugia-liviana
        D2: un grupo pierde al miembro borrado). Sus claves no se revisan: son params ya guardados."""
        ed, vivos = ediciones or {}, {c["id"] for c in self.commands}
        missing = [cid for cid in [*command_ids, *ed] if cid not in vivos]
        if missing:
            raise DocumentError(f"No existe el comando '{missing[0]}'")

        def apply():
            self.commands = [c if c["id"] not in ed else {**c, "params": ed[c["id"]]}
                             for c in self.commands if c["id"] not in set(command_ids)]

        self._mutate(apply)

    def add_attachment(self, data: bytes) -> str:
        """Guarda un archivo en el documento y devuelve su hash (id de adjunto)."""
        digest = hashlib.sha256(data).hexdigest()[:16]
        self.attachments[digest] = data
        return digest
