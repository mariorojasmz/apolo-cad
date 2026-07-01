"""Documento Apolo: log de comandos event-sourced.

El documento ES el log de comandos. La escena (sólidos B-rep) se obtiene
siempre reproduciendo el log completo, lo que hace triviales el undo/redo,
la edición paramétrica de cualquier comando pasado y la persistencia.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path

from apolo.commands.expressions import ExpressionError, resolve_all
from apolo.commands.registry import REGISTRY, CommandError, Scene, execute_command, validate_params

FORMAT_VERSION = 2  # v2 añade attachments/ (archivos STEP importados); abre v1 sin cambios


class DocumentError(Exception):
    pass


# --------- regeneración incremental: firma por comando + snapshot de estado ---------
# Seguridad: los ejecutores NUNCA mutan el shape OCCT in-place (siempre reasignan
# feat.shape o crean Features nuevas), así que un shallow-copy de cada Feature
# (compartiendo la referencia del shape, inmutable) aísla un checkpoint de las
# mutaciones de comandos posteriores SIN copiar geometría (lo caro).

def _cmd_sig(prev: str, cmd: dict) -> str:
    h = hashlib.sha1(prev.encode())
    h.update(cmd["id"].encode())
    h.update(json.dumps(cmd["params"], sort_keys=True, default=str).encode())
    return h.hexdigest()


def _copy_state(state: tuple) -> tuple:
    """Copia un estado (scene, variables, joints, mates, constraints, fasteners,
    grounds) aislándolo: Features por shallow-copy (shape compartido), dicts por copia."""
    scene, variables, joints, mates, constraints, fasteners, grounds = state
    return (
        {fid: copy.copy(f) for fid, f in scene.items()},
        dict(variables),
        copy.deepcopy(joints),
        copy.deepcopy(mates),
        copy.deepcopy(constraints),
        copy.deepcopy(fasteners),
        copy.deepcopy(grounds),
    )


class Document:
    def __init__(self, name: str = "Sin título"):
        self.name = name
        self.commands: list[dict] = []
        self.hidden: set[str] = set()
        self.scene: Scene = {}
        self.variables_raw: dict[str, str] = {}
        self.variables_resolved: dict[str, float] = {}
        self.joints: dict[str, dict] = {}
        self.mates: dict[str, dict] = {}
        self.constraints: dict[str, dict] = {}  # restricciones de riel (lazo cerrado)
        self.fasteners: dict[str, dict] = {}  # fijadores rígidos A↔B (conectividad de ensamblaje)
        self.grounds: dict[str, dict] = {}  # anclajes a tierra (validación de soundness)
        self.attachments: dict[str, bytes] = {}
        self.configurations: dict[str, dict[str, str]] = {}  # variante → {variable: expresión}
        self.colors: dict[str, str] = {}  # feature_id → color hex (apariencia)
        self.materials: dict[str, str] = {}  # feature_id → material (override BOM/peso)
        self.vertical: str = "metalmecanica"  # default de material para piezas no reconocidas
        self.motion: dict[str, list[dict]] = {}  # estudios con nombre → fotogramas [{t, values:{junta:valor}}]
        self.requirements: dict = {}  # bases de diseño del proyecto (carga, velocidad, producto…)
        self.agent_notes: list[str] = []  # memoria de proyecto del agente IA
        self._seq = 0
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._coalesce_key: str | None = None
        # caché de regeneración incremental: firma acumulada por comando + checkpoints
        # (estado tras ejecutar ciertos comandos) para reanudar desde el primer cambio.
        self._regen_sigs: list[str] = []
        self._regen_ckpts: dict[int, tuple] = {}

    # ------------------------------------------------------------- estado
    def _snapshot(self) -> dict:
        return {
            "commands": copy.deepcopy(self.commands),
            "hidden": set(self.hidden),
            "seq": self._seq,
        }

    def _restore(self, snap: dict) -> None:
        self.commands = copy.deepcopy(snap["commands"])
        self.hidden = set(snap["hidden"])
        self._seq = snap["seq"]
        self.regenerate()

    _REGEN_STRIDE = 16  # cada cuántos comandos se guarda un checkpoint de estado

    def regenerate(self) -> None:
        # 1) firma acumulada por comando del log actual
        sigs: list[str] = []
        prev = ""
        for cmd in self.commands:
            prev = _cmd_sig(prev, cmd)
            sigs.append(prev)
        # 2) primer índice que difiere respecto al último regenerate
        old = self._regen_sigs
        diverge = 0
        while diverge < len(sigs) and diverge < len(old) and sigs[diverge] == old[diverge]:
            diverge += 1
        # 3) reanudar desde el checkpoint de mayor índice ANTERIOR al cambio
        resume = -1
        for idx in sorted(self._regen_ckpts):
            if idx < diverge:
                resume = idx
            else:
                break
        if resume >= 0:
            scene, variables, joints, mates, constraints, fasteners, grounds = _copy_state(
                self._regen_ckpts[resume]
            )
            new_ckpts = {i: st for i, st in self._regen_ckpts.items() if i <= resume}
            start = resume + 1
        else:
            scene, variables, joints, mates, constraints, fasteners, grounds = (
                {}, {}, {}, {}, {}, {}, {}
            )
            new_ckpts = {}
            start = 0
        # 4) ejecutar solo la cola (desde el primer cambio) y capturar checkpoints
        last = len(self.commands) - 1
        for i in range(start, len(self.commands)):
            cmd = self.commands[i]
            try:
                execute_command(
                    scene, cmd["id"], cmd["type"], cmd["params"],
                    variables, joints, self.attachments, mates, constraints,
                    fasteners, grounds,
                )
            except CommandError as exc:
                raise DocumentError(f"Error al regenerar {cmd['id']} ({cmd['type']}): {exc}") from exc
            if i == last or i % self._REGEN_STRIDE == 0:
                new_ckpts[i] = _copy_state(
                    (scene, variables, joints, mates, constraints, fasteners, grounds)
                )
        for joint in joints.values():
            for ref in (joint["parent"], joint["child"]):
                if ref not in scene:
                    raise DocumentError(
                        f"La junta '{joint['name']}' referencia el sólido '{ref}', que ya no existe: "
                        "elimina primero la junta"
                    )
        for mate in mates.values():
            for ref in (mate["feature_a"], mate["feature_b"]):
                if ref not in scene:
                    raise DocumentError(
                        f"El mate '{mate['name']}' referencia el sólido '{ref}', que ya no existe: "
                        "elimina primero el mate"
                    )
        for con in constraints.values():
            if con["joint"] not in joints:
                raise DocumentError(
                    f"La restricción '{con['name']}' referencia la junta '{con['joint']}', "
                    "que no existe: elimina primero la restricción"
                )
        for f in fasteners.values():
            for ref in (f["a"], f["b"]):
                if ref not in scene:
                    raise DocumentError(
                        f"El fijador '{f['name']}' referencia el sólido '{ref}', que ya no existe: "
                        "elimina primero el fijador"
                    )
        for g in grounds.values():
            if g["feature"] not in scene:
                raise DocumentError(
                    f"El anclaje '{g['name']}' referencia el sólido '{g['feature']}', que ya no existe: "
                    "elimina primero el anclaje"
                )
        from apolo.assembly.mates import MateError, solve_mates

        try:
            solve_mates(scene, mates)
        except MateError as exc:
            raise DocumentError(f"Error al resolver los mates: {exc}") from exc
        for fid, feat in scene.items():
            feat.visible = fid not in self.hidden
            feat.material = self.materials.get(fid)
        self.scene = scene
        self.joints = joints
        self.mates = mates
        self.constraints = constraints
        self.fasteners = fasteners
        self.grounds = grounds
        self.variables_raw = variables
        try:
            self.variables_resolved = resolve_all(variables)
        except ExpressionError as exc:
            raise DocumentError(f"Error en las variables del proyecto: {exc}") from exc
        # commit de la caché incremental SOLO tras un regenerate completo y válido
        self._regen_sigs = sigs
        self._regen_ckpts = new_ckpts

    def _mutate(self, fn, coalesce_key: str | None = None) -> None:
        """Aplica un cambio al log con rollback automático si la regeneración
        falla. Mutaciones consecutivas con la misma coalesce_key (vista previa
        en vivo) comparten un único punto de deshacer."""
        snap = self._snapshot()
        try:
            fn()
            self.regenerate()
        except Exception:
            self._restore(snap)
            raise
        if not (coalesce_key and coalesce_key == self._coalesce_key):
            self._undo.append(snap)
        self._coalesce_key = coalesce_key
        self._redo.clear()

    def _vars_block_end(self) -> int:
        """Índice tras el bloque inicial de comandos de variables."""
        end = 0
        for cmd in self.commands:
            spec = REGISTRY.get(cmd["type"])
            if spec and spec.kind == "vars":
                end += 1
            else:
                break
        return end

    # ----------------------------------------------------------- comandos
    def _append_record(self, cmd_type: str, params: dict) -> str:
        """Asigna cmd_id, incrementa seq e inserta el record en el log (los
        comandos 'vars' se hoist-ean al principio para que cualquier geometría
        pueda usarlos). NO valida ni regenera: lo usan execute() y execute_many()."""
        self._seq += 1
        cmd_id = f"c{self._seq}"
        record = {"id": cmd_id, "type": cmd_type, "params": params}
        spec = REGISTRY.get(cmd_type)
        if spec is not None and spec.kind == "vars":
            self.commands.insert(self._vars_block_end(), record)
        else:
            self.commands.append(record)
        return cmd_id

    def execute(self, cmd_type: str, params: dict) -> str:
        validate_params(cmd_type, params, self.variables_raw)
        holder: dict[str, str] = {}

        def apply():
            holder["id"] = self._append_record(cmd_type, params)

        self._mutate(apply)
        return holder["id"]

    def execute_many(self, actions: list[dict]) -> list[str]:
        """Ejecuta un lote ATÓMICO con UN solo regenerate y UN solo paso de undo.
        '$k' (1-based) referencia el cmd_id de la k-ésima acción del lote. NO
        pre-valida por comando: el regenerate final valida en orden con el dict de
        variables en construcción (así un set_variable seguido de su uso en el mismo
        lote funciona). Si la resolución de '$k' o el regenerate fallan, revierte
        TODO el lote (o todo o nada)."""
        from apolo.batch import resolve_refs  # perezoso: evita ciclo document<->batch

        if not actions:
            return []
        snap = self._snapshot()
        created: list[str | None] = []
        try:
            for action in actions:
                params = resolve_refs(action.get("params") or {}, created)
                created.append(self._append_record(action["type"], params))
            self.regenerate()
        except Exception:
            self._restore(snap)
            raise
        self._undo.append(snap)
        self._redo.clear()
        self._coalesce_key = None
        return [c for c in created if c is not None]

    def edit_many(self, edits: list[dict], merge: bool = False) -> list[str]:
        """Edita VARIOS comandos en UN lote atómico: un solo regenerate y un solo paso
        de undo. edits = [{"command_id": "...", "params": {...}}, ...]. Como execute_many,
        NO pre-valida por comando (el regenerate final valida con las variables en
        construcción, así editar un set_variable + su uso en el mismo lote funciona).
        Rollback total si algo falla. merge=True hace PATCH superficial por comando (un
        sub-objeto como position/rotation se reemplaza entero), igual que edit."""
        if not edits:
            return []
        snap = self._snapshot()
        touched: list[str] = []
        try:
            for e in edits:
                cid = e["command_id"]
                idx = next(
                    (i for i, c in enumerate(self.commands) if c["id"] == cid), None
                )
                if idx is None:
                    raise DocumentError(f"No existe el comando '{cid}'")
                params = e.get("params") or {}
                if merge:
                    params = {**self.commands[idx]["params"], **params}
                self.commands[idx]["params"] = params
                touched.append(cid)
            self.regenerate()
        except Exception:
            self._restore(snap)
            raise
        self._undo.append(snap)
        self._redo.clear()
        self._coalesce_key = None
        return touched

    def preview(self, actions: list[dict]) -> tuple[dict, list[str]]:
        """Aplica `actions` (formato execute_many: [{type, params}, ...]) sobre una COPIA
        del documento y devuelve (scene_resultante, nuevos_command_ids) SIN mutar este
        documento — para un 'ghost render' de una propuesta antes de ejecutarla de verdad.
        Reusa la caché de regenerate (incremental, rápido) en vez de un rebuild en frío.
        Si las acciones fallan, propaga el error (la copia se descarta sola)."""
        import copy

        clone = Document(self.name)
        clone.commands = copy.deepcopy(self.commands)
        clone.hidden = set(self.hidden)
        clone._seq = self._seq
        clone.variables_raw = dict(self.variables_raw)
        clone._regen_sigs = list(self._regen_sigs)
        clone._regen_ckpts = dict(self._regen_ckpts)  # comparte refs de shape OCCT (read-only)
        if actions:
            new_ids = clone.execute_many(actions)
        else:
            clone.regenerate()
            new_ids = []
        return clone.scene, new_ids

    def edit(
        self, command_id: str, params: dict, coalesce: bool = False, merge: bool = False
    ) -> str:
        """Edita los params de un comando. Por defecto REEMPLAZA (los campos omitidos
        vuelven a su default). Con `merge=True` hace PATCH superficial: combina con los
        params actuales (un sub-objeto como position/rotation se reemplaza entero).
        Devuelve el command_id editado."""
        idx = next((i for i, c in enumerate(self.commands) if c["id"] == command_id), None)
        if idx is None:
            raise DocumentError(f"No existe el comando '{command_id}'")
        if merge:
            params = {**self.commands[idx]["params"], **params}
        validate_params(self.commands[idx]["type"], params, self.variables_raw)

        def apply():
            self.commands[idx]["params"] = params

        self._mutate(apply, coalesce_key=f"edit:{command_id}" if coalesce else None)
        return command_id

    def remove_commands(self, command_ids: list[str]) -> None:
        """Elimina comandos del log y regenera; revierte si algo queda roto."""
        missing = [cid for cid in command_ids if not any(c["id"] == cid for c in self.commands)]
        if missing:
            raise DocumentError(f"No existe el comando '{missing[0]}'")

        def apply():
            self.commands = [c for c in self.commands if c["id"] not in set(command_ids)]

        self._mutate(apply)

    def add_attachment(self, data: bytes) -> str:
        """Guarda un archivo en el documento y devuelve su hash (id de adjunto)."""
        digest = hashlib.sha256(data).hexdigest()[:16]
        self.attachments[digest] = data
        return digest

    # ------------------------------------------------------- configuraciones
    def save_configuration(self, name: str) -> None:
        """Captura los valores actuales de TODAS las variables como variante."""
        if not self.variables_raw:
            raise DocumentError("No hay variables que guardar: define variables primero")
        self.configurations[name] = dict(self.variables_raw)

    def apply_configuration(self, name: str) -> None:
        """Aplica una variante: edita los set_variable correspondientes y
        regenera (un único paso de deshacer)."""
        config = self.configurations.get(name)
        if config is None:
            raise DocumentError(f"No existe la configuración '{name}'")

        def apply():
            for cmd in self.commands:
                if cmd["type"] == "set_variable":
                    var = cmd["params"].get("name")
                    if var in config:
                        cmd["params"] = {"name": var, "expression": str(config[var])}

        self._mutate(apply)

    def delete_configuration(self, name: str) -> None:
        if name not in self.configurations:
            raise DocumentError(f"No existe la configuración '{name}'")
        del self.configurations[name]

    def set_color(self, feature_id: str, color: str | None) -> None:
        if feature_id not in self.scene:
            raise DocumentError(f"No existe el sólido '{feature_id}'")
        if color:
            self.colors[feature_id] = color
        else:
            self.colors.pop(feature_id, None)

    def set_material(self, feature_id: str, material: str | None) -> None:
        if feature_id not in self.scene:
            raise DocumentError(f"No existe el sólido '{feature_id}'")
        if material:
            self.materials[feature_id] = material
            self.scene[feature_id].material = material
        else:
            self.materials.pop(feature_id, None)
            self.scene[feature_id].material = None

    def set_vertical(self, vertical: str) -> None:
        if vertical not in ("metalmecanica", "carpinteria"):
            raise DocumentError("vertical debe ser 'metalmecanica' o 'carpinteria'")
        self.vertical = vertical

    def default_material(self) -> str:
        """Material por defecto de piezas a-medida no reconocidas (según vertical)."""
        return "madera" if self.vertical == "carpinteria" else "acero"

    def set_motion(self, name: str, keyframes: list[dict]) -> None:
        """Define los fotogramas clave de un estudio de movimiento CON NOMBRE (metadato, no
        geometría). Lista vacía → borra el estudio. Pueden coexistir varios estudios."""
        name = str(name).strip()
        if not name:
            raise DocumentError("El estudio de movimiento necesita un nombre")
        clean: list[dict] = []
        for kf in keyframes:
            try:
                t = float(kf["t"])
            except (KeyError, TypeError, ValueError) as exc:
                raise DocumentError("Cada fotograma necesita un tiempo 't' numérico") from exc
            if t < 0:
                raise DocumentError("El tiempo del fotograma no puede ser negativo")
            values = kf.get("values") or {}
            if not isinstance(values, dict):
                raise DocumentError("Los valores del fotograma deben ser {junta: valor}")
            clean.append({"t": t, "values": {str(n): float(v) for n, v in values.items()}})
        if clean:
            self.motion[name] = sorted(clean, key=lambda k: k["t"])
        else:
            self.motion.pop(name, None)

    def delete_motion(self, name: str) -> None:
        """Elimina un estudio de movimiento por nombre (no falla si no existe)."""
        self.motion.pop(str(name).strip(), None)

    # claves de requisitos con convención NUMÉRICA (se coercionan a float > 0)
    _REQ_NUMERIC = (
        "carga_kg", "largo_paquete_mm", "ancho_paquete_mm", "alto_paquete_mm",
        "velocidad_m_s", "inclinacion_deg", "temperatura_c",
    )

    def set_requirements(self, fields: dict) -> None:
        """Define las BASES DE DISEÑO del proyecto (metadato, como motion): contra
        qué se valida la máquina. Reemplaza el dict completo; `{}` las borra.
        Claves de convención numéricas (carga_kg, velocidad_m_s, …) se validan
        como float; el resto son texto libre (producto, entorno, normativa, notas)."""
        if not isinstance(fields, dict):
            raise DocumentError("Los requisitos deben ser un objeto {clave: valor}")
        clean: dict = {}
        for key, value in fields.items():
            key = str(key).strip()
            if not key or value is None or value == "":
                continue
            if key in self._REQ_NUMERIC:
                try:
                    num = float(value)
                except (TypeError, ValueError) as exc:
                    raise DocumentError(f"El requisito '{key}' debe ser numérico") from exc
                # la inclinación puede ser 0 o negativa (declive); el resto, positivo
                if key != "inclinacion_deg" and num <= 0:
                    raise DocumentError(f"El requisito '{key}' debe ser > 0")
                clean[key] = num
            elif isinstance(value, (str, int, float, bool)):
                clean[key] = value
            else:
                raise DocumentError(f"El requisito '{key}' debe ser escalar (texto o número)")
        self.requirements = clean

    def set_visibility(self, feature_id: str, visible: bool) -> None:
        if feature_id not in self.scene:
            raise DocumentError(f"No existe el sólido '{feature_id}'")
        if visible:
            self.hidden.discard(feature_id)
        else:
            self.hidden.add(feature_id)
        self.scene[feature_id].visible = visible

    # --------------------------------------------------------- undo / redo
    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        if not self._undo:
            raise DocumentError("Nada que deshacer")
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        self._coalesce_key = None

    def redo(self) -> None:
        if not self._redo:
            raise DocumentError("Nada que rehacer")
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        self._coalesce_key = None

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
                        "colors": self.colors,
                        "materials": self.materials,
                        "vertical": self.vertical,
                        "motion": self.motion,
                        "requirements": self.requirements,
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
    def from_apolo_bytes(cls, data: bytes) -> "Document":
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
        doc.configurations = manifest.get("configurations", {})
        doc.colors = manifest.get("colors", {})
        doc.materials = manifest.get("materials", {})
        doc.vertical = manifest.get("vertical", "metalmecanica")
        _m = manifest.get("motion", {})
        # migración: proyectos viejos guardaban el motion como UNA lista de fotogramas
        doc.motion = ({"Estudio 1": _m} if _m else {}) if isinstance(_m, list) else dict(_m)
        doc.requirements = manifest.get("requirements", {})
        doc.agent_notes = manifest.get("agent_notes", [])
        doc._seq = manifest.get("seq", len(commands))
        doc.regenerate()
        return doc

    @classmethod
    def load(cls, path: str | Path) -> "Document":
        return cls.from_apolo_bytes(Path(path).read_bytes())
