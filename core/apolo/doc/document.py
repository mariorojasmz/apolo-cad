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
import os
import re
import zipfile
from pathlib import Path

from apolo.commands.expressions import ExpressionError, resolve_all
from apolo.commands.registry import REGISTRY, CommandError, Scene, execute_command, validate_params

FORMAT_VERSION = 2  # v2 añade attachments/ (archivos STEP importados); abre v1 sin cambios

# Modo ESTRICTO (V6.1): tras cada mutación exitosa, si hay violaciones de integridad
# el documento revierte en vez de quedar a medias. Off por defecto (la carga tolerante
# y el fallback de render cubren los degradados en operación); la suite de tortura lo
# activa por monkeypatch del ATRIBUTO ``document._STRICT`` — por eso se lee como global
# del módulo en cada _check_strict (no se captura en un local).
_STRICT = os.environ.get("APOLO_STRICT") == "1"

# id de comando c-numérico (para la guardia de seq y check_integrity)
_CID_RE = re.compile(r"^c(\d+)$")


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
    grounds, groups) aislándolo: Features por shallow-copy (shape compartido), dicts
    por copia."""
    scene, variables, joints, mates, constraints, fasteners, grounds, groups = state
    return (
        {fid: copy.copy(f) for fid, f in scene.items()},
        dict(variables),
        copy.deepcopy(joints),
        copy.deepcopy(mates),
        copy.deepcopy(constraints),
        copy.deepcopy(fasteners),
        copy.deepcopy(grounds),
        copy.deepcopy(groups),
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
        self.groups: dict[str, dict] = {}  # sub-ensamblajes por command_ids (V5.2, del log)
        self.attachments: dict[str, bytes] = {}
        self.configurations: dict[str, dict[str, str]] = {}  # variante → {variable: expresión}
        self.colors: dict[str, str] = {}  # feature_id → color hex (apariencia)
        self.materials: dict[str, str] = {}  # feature_id → material (override BOM/peso)
        self.sketch_guides: set[str] = set()  # command_ids de boceto-guía (blockout): fuera de BOM/masa/interferencia/FEA; el agente los consume y borra
        self.vertical: str = "metalmecanica"  # default de material para piezas no reconocidas
        self.motion: dict[str, list[dict]] = {}  # estudios con nombre → fotogramas [{t, values:{junta:valor}}]
        self.requirements: dict = {}  # bases de diseño del proyecto (carga, velocidad, producto…)
        self.fea: dict[str, dict] = {}  # feature_id → resumen del último FEA (metadato)
        self.agent_notes: list[str] = []  # memoria de proyecto del agente IA
        # comandos SUPRIMIDOS por una carga tolerante (transitorio: NUNCA se persiste en
        # el manifest; se recalcula en cada regenerate — vacío en modo estricto)
        self.regen_suppressed: list[dict] = []
        self._seq = 0
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._coalesce_key: str | None = None
        # caché de regeneración incremental: firma acumulada por comando + checkpoints
        # (estado tras ejecutar ciertos comandos) para reanudar desde el primer cambio.
        self._regen_sigs: list[str] = []
        self._regen_ckpts: dict[int, tuple] = {}

    _UNDO_CAP = 50  # cota del historial de deshacer (los snapshots retienen la caché de regen)

    # ------------------------------------------------------------- estado
    def _snapshot(self) -> dict:
        # la caché de regen viaja en el snapshot (Fix C): al restaurar se repone ANTES
        # de regenerar → el rollback resume del último checkpoint del log viejo (replay
        # de ~0 comandos) e inmune a un fallo repetido durante la propia restauración.
        return {
            "commands": copy.deepcopy(self.commands),
            "hidden": set(self.hidden),
            "seq": self._seq,
            "regen": (list(self._regen_sigs), dict(self._regen_ckpts)),
        }

    def _restore(self, snap: dict) -> None:
        self.commands = copy.deepcopy(snap["commands"])
        self.hidden = set(snap["hidden"])
        self._seq = snap["seq"]
        regen = snap.get("regen")
        if regen is not None:
            self._regen_sigs = list(regen[0])
            self._regen_ckpts = dict(regen[1])  # comparte refs de shape OCCT (read-only)
        self.regenerate()

    _REGEN_STRIDE = 16  # cada cuántos comandos se guarda un checkpoint de estado

    def _ckpts_ok(self) -> bool:
        """La caché de checkpoints es estructuralmente SANA (segura de usar): claves int
        (no bool) en el rango del log y estado = tupla de 8 con dict en [0]. Cualquier
        anomalía → el caller fuerza replay completo en vez de reventar (blindaje Fix B).
        Las firmas (sigs) NO se validan: son strings y comparar con basura da False sin
        petar, y un largo distinto es NORMAL entre append y regenerate."""
        n = len(self.commands)
        try:
            for k, st in self._regen_ckpts.items():
                if isinstance(k, bool) or not isinstance(k, int) or not (0 <= k < n):
                    return False
                if not (isinstance(st, tuple) and len(st) == 8 and isinstance(st[0], dict)):
                    return False
        except Exception:
            return False
        return True

    def _prune_or_raise(self, scene, joints, mates, constraints, fasteners, grounds,
                        tolerant: bool, suppressed: list) -> None:
        """Valida que juntas/mates/restricciones/fijadores/anclajes referencian entidades
        VIVAS. Estricto: lanza DocumentError al primer huérfano. Tolerante (solo en carga):
        ELIMINA la entidad huérfana del estado EN MEMORIA (el LOG jamás se toca) y la
        reporta en `suppressed`. Orden: juntas antes que restricciones (una restricción
        cuya junta se podó también queda huérfana)."""
        def bad(kind, name, cmd_id, msg) -> bool:
            if tolerant:
                suppressed.append({"command_id": cmd_id, "type": kind, "error": msg})
                return True
            raise DocumentError(msg)

        for name in list(joints):
            j = joints[name]
            ref = next((r for r in (j["parent"], j["child"]) if r not in scene), None)
            if ref is not None and bad("add_joint", name, j.get("command_id"),
                    f"La junta '{name}' referencia el sólido '{ref}', que ya no existe: "
                    "elimina primero la junta"):
                del joints[name]
        for name in list(mates):
            m = mates[name]
            ref = next((r for r in (m["feature_a"], m["feature_b"]) if r not in scene), None)
            if ref is not None and bad("add_mate", name, m.get("command_id"),
                    f"El mate '{name}' referencia el sólido '{ref}', que ya no existe: "
                    "elimina primero el mate"):
                del mates[name]
        for name in list(constraints):
            con = constraints[name]
            if con["joint"] not in joints and bad("add_constraint", name, con.get("command_id"),
                    f"La restricción '{name}' referencia la junta '{con['joint']}', "
                    "que no existe: elimina primero la restricción"):
                del constraints[name]
        for name in list(fasteners):
            f = fasteners[name]
            ref = next((r for r in (f["a"], f["b"]) if r not in scene), None)
            if ref is not None and bad("fasten", name, f.get("command_id"),
                    f"El fijador '{name}' referencia el sólido '{ref}', que ya no existe: "
                    "elimina primero el fijador"):
                del fasteners[name]
        for name in list(grounds):
            g = grounds[name]
            if g["feature"] not in scene and bad("ground", name, g.get("command_id"),
                    f"El anclaje '{name}' referencia el sólido '{g['feature']}', que ya no existe: "
                    "elimina primero el anclaje"):
                del grounds[name]

    def regenerate(self, *, tolerant: bool = False) -> None:
        """Reproduce el log y REEMPLAZA el estado del documento de forma ATÓMICA: todo se
        construye en variables LOCALES y solo al final, en UN bloque de asignaciones que
        no puede lanzar, se vuelca a `self`. Si algo revienta antes (executor, referencia
        colgando, mates, variables), `self` queda INTACTO (todo o nada — Fix C).

        Con ``tolerant=True`` (SOLO en cargas: el arranque y las rutas de open/restore)
        un comando que revienta se SUPRIME y se anota en `regen_suppressed`, y las
        entidades huérfanas se podan del estado en memoria — el LOG nunca se toca. Las
        MUTACIONES (_mutate/execute_many/edit_many) llaman SIEMPRE en modo estricto."""
        from apolo.assembly.groups import assign_feature_groups
        from apolo.assembly.mates import MateError, solve_mates

        # 1) firma acumulada por comando del log actual
        sigs: list[str] = []
        prev = ""
        for cmd in self.commands:
            prev = _cmd_sig(prev, cmd)
            sigs.append(prev)
        # 2) caché incremental blindada (Fix B): si los checkpoints están corruptos, se
        #    ignoran → replay completo, NUNCA se lanza por culpa de la caché
        ckpts = self._regen_ckpts if self._ckpts_ok() else {}
        old = self._regen_sigs
        # 3) primer índice que difiere respecto al último regenerate
        diverge = 0
        while diverge < len(sigs) and diverge < len(old) and sigs[diverge] == old[diverge]:
            diverge += 1
        # 4) reanudar desde el checkpoint de mayor índice ANTERIOR al cambio
        resume = -1
        for idx in sorted(ckpts):
            if idx < diverge:
                resume = idx
            else:
                break
        if resume >= 0:
            (scene, variables, joints, mates, constraints, fasteners, grounds,
             groups) = _copy_state(ckpts[resume])
            new_ckpts = {i: st for i, st in ckpts.items() if i <= resume}
            start = resume + 1
        else:
            scene, variables, joints, mates, constraints, fasteners, grounds, groups = (
                {}, {}, {}, {}, {}, {}, {}, {}
            )
            new_ckpts = {}
            start = 0
        suppressed: list[dict] = []
        # 5) ejecutar solo la cola (desde el primer cambio) y capturar checkpoints
        last = len(self.commands) - 1
        for i in range(start, len(self.commands)):
            cmd = self.commands[i]
            try:
                execute_command(
                    scene, cmd["id"], cmd["type"], cmd["params"],
                    variables, joints, self.attachments, mates, constraints,
                    fasteners, grounds, groups,
                )
            except CommandError as exc:
                if tolerant:
                    suppressed.append(
                        {"command_id": cmd["id"], "type": cmd["type"], "error": str(exc)}
                    )
                else:
                    raise DocumentError(
                        f"Error al regenerar {cmd['id']} ({cmd['type']}): {exc}"
                    ) from exc
            if i == last or i % self._REGEN_STRIDE == 0:
                new_ckpts[i] = _copy_state(
                    (scene, variables, joints, mates, constraints, fasteners, grounds, groups)
                )
        # 6) referencias colgando: estricto lanza, tolerante poda + reporta
        self._prune_or_raise(
            scene, joints, mates, constraints, fasteners, grounds, tolerant, suppressed
        )
        try:
            solve_mates(scene, mates)
        except MateError as exc:
            if tolerant:
                suppressed.append({"command_id": None, "type": "mates", "error": str(exc)})
            else:
                raise DocumentError(f"Error al resolver los mates: {exc}") from exc
        # membresía de grupos: campo DERIVADO por command_id (integridad TOLERANTE —
        # un member cuyo comando desapareció se reporta vía missing_members, no falla)
        assign_feature_groups(scene, groups)
        for fid, feat in scene.items():
            feat.visible = fid not in self.hidden
            # .get con default: un executor puede haber seteado ya el material de la
            # pieza (insert_project importa los del proyecto origen) — no pisarlo
            feat.material = self.materials.get(fid, feat.material)
            # boceto-guía DERIVADO por command_id (como la membresía de grupos)
            feat.is_guide = feat.command_id in self.sketch_guides
        # variables resueltas en LOCAL (antes de tocar self: si truena, self intacto)
        try:
            variables_resolved = resolve_all(variables)
        except ExpressionError as exc:
            raise DocumentError(f"Error en las variables del proyecto: {exc}") from exc
        # 7) BLOQUE ÚNICO de asignaciones — a partir de aquí NADA puede lanzar (atomicidad)
        self.scene = scene
        self.joints = joints
        self.mates = mates
        self.constraints = constraints
        self.fasteners = fasteners
        self.grounds = grounds
        self.groups = groups
        self.variables_raw = variables
        self.variables_resolved = variables_resolved
        self.regen_suppressed = suppressed
        self._regen_sigs = sigs
        self._regen_ckpts = new_ckpts

    # ------------------------------------------------- contrato de integridad (V6.1)
    def check_integrity(self) -> list[str]:
        """Verifica los INVARIANTES del documento y devuelve una lista de violaciones,
        cada una un string ACCIONABLE (lista vacía = íntegro). Es READ-ONLY PURO: no
        muta el documento ni ninguna caché, y NUNCA lanza (cualquier fallo interno se
        reporta como violación). Una entrada con prefijo ``"degradado: "`` NO es un
        error de corrección: solo señala pérdida de instancing (definición desalojada
        de DEFINITIONS) que el fallback de render ya cubre — el modo estricto la ignora."""
        from apolo.commands.registry import DEFINITIONS

        issues: list[str] = []
        log_ids = {c["id"] for c in self.commands}

        def _cmd_alive(cid: str) -> bool:
            # command_id directo del log, o sintético '{cmd}_{orig}' de insert_project
            # cuyo prefijo (el comando anfitrión) sigue vivo
            return cid in log_ids or cid.split("_", 1)[0] in log_ids

        # features: id coherente, comando vivo, contrato de instancia (mesh_key⇔matrix)
        for fid, feat in self.scene.items():
            if feat.id != fid:
                issues.append(f"la feature '{fid}' guarda id interno '{feat.id}' (deben coincidir)")
            if not _cmd_alive(feat.command_id):
                issues.append(
                    f"la feature '{fid}' apunta al comando '{feat.command_id}', ausente del log"
                )
            if (feat.mesh_key is None) != (feat.matrix is None):
                issues.append(
                    f"la feature '{fid}' tiene instancia a medias "
                    f"(mesh_key={feat.mesh_key!r}, matrix={'set' if feat.matrix else None})"
                )
            elif feat.mesh_key is not None and feat.mesh_key not in DEFINITIONS:
                issues.append(
                    f"degradado: la feature '{fid}' referencia la definición '{feat.mesh_key}', "
                    "desalojada de DEFINITIONS (el render usa el shape mundial: solo se pierde instancing)"
                )

        # conectividad: toda referencia a una feature/junta debe existir
        for jname, j in self.joints.items():
            for ref in (j.get("parent"), j.get("child")):
                if ref not in self.scene:
                    issues.append(f"la junta '{jname}' referencia el sólido '{ref}', ausente de la escena")
        for mname, m in self.mates.items():
            for ref in (m.get("feature_a"), m.get("feature_b")):
                if ref not in self.scene:
                    issues.append(f"el mate '{mname}' referencia el sólido '{ref}', ausente de la escena")
        for cname, con in self.constraints.items():
            if con.get("joint") not in self.joints:
                issues.append(f"la restricción '{cname}' referencia la junta '{con.get('joint')}', ausente")
        for fname, f in self.fasteners.items():
            for ref in (f.get("a"), f.get("b")):
                if ref not in self.scene:
                    issues.append(f"el fijador '{fname}' referencia el sólido '{ref}', ausente de la escena")
        for gname, g in self.grounds.items():
            if g.get("feature") not in self.scene:
                issues.append(f"el anclaje '{gname}' referencia el sólido '{g.get('feature')}', ausente")

        # grupos: parent declarado + sin ciclos. La membresía es TOLERANTE por diseño
        # (un member cuyo comando se borró se reporta vía missing_members, no aquí).
        for gname, g in self.groups.items():
            parent = g.get("parent")
            if parent is not None and parent not in self.groups:
                issues.append(f"el grupo '{gname}' cuelga del padre '{parent}', que no existe")
            seen: set[str] = set()
            cur = gname
            while cur is not None:
                if cur in seen:
                    issues.append(f"el grupo '{gname}' forma un ciclo de parents")
                    break
                seen.add(cur)
                nxt = self.groups.get(cur)
                cur = nxt.get("parent") if nxt else None

        # caché de regeneración incremental (blindaje del fix B)
        if len(self._regen_sigs) != len(self.commands):
            issues.append(
                f"_regen_sigs tiene {len(self._regen_sigs)} firmas para {len(self.commands)} comandos"
            )
        n = len(self.commands)
        for k, st in self._regen_ckpts.items():
            if not isinstance(k, int) or not (0 <= k < n):
                issues.append(f"checkpoint con clave inválida {k!r} (fuera de [0,{n}))")
            elif not (isinstance(st, tuple) and len(st) == 8 and isinstance(st[0], dict)):
                issues.append(f"checkpoint {k} mal formado (se esperaba tupla de 8 con dict en [0])")

        # seq monótono: nunca por debajo del mayor id c-numérico del log (evita colisiones)
        max_suffix = 0
        for cid in log_ids:
            mo = _CID_RE.match(cid)
            if mo:
                max_suffix = max(max_suffix, int(mo.group(1)))
        if self._seq < max_suffix:
            issues.append(f"_seq={self._seq} es menor que el mayor id del log (c{max_suffix})")

        # variables resueltas coherentes con las crudas
        try:
            expected = resolve_all(self.variables_raw)
        except Exception as exc:  # variables circulares/inválidas: ES una violación
            issues.append(f"las variables del proyecto no resuelven: {exc}")
        else:
            if expected != self.variables_resolved:
                issues.append("variables_resolved no coincide con resolve_all(variables_raw)")

        # dedup conservando orden (varias referencias pueden apuntar a lo mismo)
        out: list[str] = []
        for msg in issues:
            if msg not in out:
                out.append(msg)
        return out

    def _check_strict(self) -> None:
        """En modo estricto, lanza si la integridad quedó violada (excluyendo los
        'degradado', que el fallback de render cubre). El caller (_mutate/execute_many/
        edit_many) revierte al snapshot previo, así una mutación nunca deja el doc a
        medias. Se lee ``_STRICT`` como global del módulo para permitir el monkeypatch."""
        if not _STRICT:
            return
        issues = [i for i in self.check_integrity() if not i.startswith("degradado")]
        if issues:
            raise DocumentError(
                "El documento quedó en un estado inconsistente tras la operación:\n  - "
                + "\n  - ".join(issues)
            )

    def _mutate(self, fn, coalesce_key: str | None = None) -> None:
        """Aplica un cambio al log con rollback automático si la regeneración
        falla. Mutaciones consecutivas con la misma coalesce_key (vista previa
        en vivo) comparten un único punto de deshacer."""
        snap = self._snapshot()
        try:
            fn()
            self.regenerate()
            self._check_strict()
        except Exception:
            self._restore(snap)
            raise
        if not (coalesce_key and coalesce_key == self._coalesce_key):
            self._undo.append(snap)
            del self._undo[: -self._UNDO_CAP]  # acota el historial (snapshots retienen caché)
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
            self._check_strict()
        except Exception:
            self._restore(snap)
            raise
        self._undo.append(snap)
        del self._undo[: -self._UNDO_CAP]
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
            self._check_strict()
        except Exception:
            self._restore(snap)
            raise
        self._undo.append(snap)
        del self._undo[: -self._UNDO_CAP]
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
        clone.attachments = dict(self.attachments)  # import_step/insert_project los leen
        clone.materials = dict(self.materials)
        clone.sketch_guides = set(self.sketch_guides)
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

    def set_fea_result(self, feature_id: str, summary: dict | None) -> None:
        """Guarda (o borra con None) el resumen del último FEA de una pieza.
        Metadato de manifest (como motion/requirements): NO entra al log ni a los
        checkpoints; la memoria de cálculo lo consume con chequeo de vigencia."""
        fid = str(feature_id).strip()
        if not fid:
            raise DocumentError("El resultado FEA necesita el id de la pieza")
        if summary is None:
            self.fea.pop(fid, None)
        else:
            self.fea[fid] = dict(summary)

    # claves de requisitos con convención NUMÉRICA (se coercionan a float > 0)
    _REQ_NUMERIC = (
        "carga_kg", "largo_paquete_mm", "ancho_paquete_mm", "alto_paquete_mm",
        "velocidad_m_s", "inclinacion_deg", "temperatura_c", "tipo_cambio",
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

    def set_sketch_guide(self, feature_id: str, guide: bool) -> None:
        """Marca/desmarca el sólido (y TODAS las piezas de su comando) como boceto-guía
        (blockout): geometría de INTENCIÓN excluida de BOM/masa/interferencia/FEA. Metadato
        de manifest (como colors/materials): no entra al log ni a los checkpoints."""
        feat = self.scene.get(feature_id)
        if feat is None:
            raise DocumentError(f"No existe el sólido '{feature_id}'")
        cmd_id = feat.command_id
        if guide:
            self.sketch_guides.add(cmd_id)
        else:
            self.sketch_guides.discard(cmd_id)
        for f in self.scene.values():  # un comando puede emitir varias piezas (create_frame)
            if f.command_id == cmd_id:
                f.is_guide = guide

    # --------------------------------------------------------- undo / redo
    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        # patrón peek-then-commit (Fix C): NO se saca el snapshot de la pila hasta saber
        # que la restauración sobrevivió. Si _restore revienta, se intenta volver al
        # estado actual (los ckpts intactos lo hacen O(1)) y el historial NO se pierde.
        if not self._undo:
            raise DocumentError("Nada que deshacer")
        snap_actual = self._snapshot()
        try:
            self._restore(self._undo[-1])
        except Exception:
            try:
                self._restore(snap_actual)
            except Exception:
                pass
            raise
        self._redo.append(snap_actual)
        self._undo.pop()
        self._coalesce_key = None

    def redo(self) -> None:
        if not self._redo:
            raise DocumentError("Nada que rehacer")
        snap_actual = self._snapshot()
        try:
            self._restore(self._redo[-1])
        except Exception:
            try:
                self._restore(snap_actual)
            except Exception:
                pass
            raise
        self._undo.append(snap_actual)
        self._redo.pop()
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
                        "sketch_guides": sorted(self.sketch_guides),
                        "vertical": self.vertical,
                        "motion": self.motion,
                        "requirements": self.requirements,
                        "fea": self.fea,
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
        cls, data: bytes, *, regenerate: bool = True, tolerant: bool = False
    ) -> "Document":
        """Con ``regenerate=False`` devuelve el documento SIN reproducir el log —
        para editarlo antes del primer replay (sandbox de insert_project). Con
        ``tolerant=True`` (SOLO en rutas de CARGA: arranque, open, restore) un comando
        que revienta se SUPRIME en vez de abortar la apertura — reportado en
        ``regen_suppressed``, con el LOG intacto. Las mutaciones cargan estrictas."""
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
        doc.sketch_guides = set(manifest.get("sketch_guides", []))
        doc.vertical = manifest.get("vertical", "metalmecanica")
        _m = manifest.get("motion", {})
        # migración: proyectos viejos guardaban el motion como UNA lista de fotogramas
        doc.motion = ({"Estudio 1": _m} if _m else {}) if isinstance(_m, list) else dict(_m)
        doc.requirements = manifest.get("requirements", {})
        doc.fea = manifest.get("fea", {})
        doc.agent_notes = manifest.get("agent_notes", [])
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
            doc.regenerate(tolerant=tolerant)
        return doc

    @classmethod
    def load(cls, path: str | Path) -> "Document":
        return cls.from_apolo_bytes(Path(path).read_bytes())
