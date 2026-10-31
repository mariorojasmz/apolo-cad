"""Documento Apolo: log de comandos event-sourced.

El documento ES el log de comandos. La escena (sólidos B-rep) se obtiene
siempre reproduciendo el log completo, lo que hace triviales el undo/redo,
la edición paramétrica de cualquier comando pasado y la persistencia.

`Document` se arma con cuatro mixins (plan partir-nucleo-congelado, F5): `edicion.py`,
`metadatos.py`, `integridad.py` y `persistencia.py`. Aquí se queda lo que lee un global que
los tests REASIGNAN en este módulo (`execute_command`, `resolve_all`, `_STRICT`): el estado,
`regenerate`, el modo estricto, las mutaciones, deshacer y `preview` (construye `Document`).
"""

from __future__ import annotations

import copy
import os

from apolo.commands.expressions import ExpressionError, resolve_all
from apolo.commands.registry import REGISTRY, CommandError, Scene, execute_command
from apolo.commands.state import RegenState
from apolo.doc import carril, sello, solo_lectura
from apolo.doc import pasos as _pasos
from apolo.doc.edicion import EdicionDocumento
from apolo.doc.errors import ContractError, DocumentError  # noqa: F401 — se re-exportan
from apolo.doc.integridad import IntegridadDocumento
from apolo.doc.metadatos import MetadatosDocumento
from apolo.doc.por_comando import de_la_pieza
from apolo.doc.persistencia import (  # noqa: F401 — se re-exportan (casa: persistencia)
    _CID_RE,
    FORMAT_VERSION,
    PersistenciaDocumento,
)

# Modo ESTRICTO (V6.1): tras cada mutación exitosa, si hay violaciones de integridad
# el documento revierte en vez de quedar a medias. Off por defecto (la carga tolerante
# y el fallback de render cubren los degradados en operación); la suite de tortura lo
# activa por monkeypatch del ATRIBUTO ``document._STRICT`` — por eso se lee como global
# del módulo en cada _check_strict (no se captura en un local).
_STRICT = os.environ.get("APOLO_STRICT") == "1"


# --------- regeneración incremental: firma por comando + snapshot de estado ---------
# Los executors NUNCA mutan el shape OCCT in-place → un checkpoint comparte los shapes sin
# copiar geometría (`RegenState.copy()`). Firma = previa + id + params + versión ≠ 1 (D9).
# Firmas y checkpoints se indexan sobre los comandos de ESCENA: el carril no entra (V8.1 D1),
# salvo el hash de lo que lee un `lee_carril` (V8.5 D1): `carril.firmas`/`carril.cmd_sig`.
_cmd_sig = carril.cmd_sig  # el nombre histórico (lo importan los tests)


class Document(EdicionDocumento, MetadatosDocumento, IntegridadDocumento, PersistenciaDocumento):
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
        # D9 de puerta-fuera-de-catalogo: los de la RAÍZ de un patrón, que heredan sus copias
        self.materiales_por_comando: dict[str, str] = {}  # command_id → material (doc/por_comando)
        self.colores_por_comando: dict[str, str] = {}  # command_id → color hex
        self.sketch_guides: set[str] = set()  # command_ids de boceto-guía (blockout): fuera de BOM/masa/interferencia/FEA; el agente los consume y borra
        self.vertical: str = "metalmecanica"  # default de material para piezas no reconocidas
        self.motion: dict[str, list[dict]] = {}  # estudios con nombre → fotogramas [{t, values:{junta:valor}}]
        self.requirements: dict = {}  # bases de diseño del proyecto (carga, velocidad, producto…)
        self.comercial: dict = {}  # a quién va la cotización: titulo, cliente, numero, revision (library/comercial)
        self.fea: dict[str, dict] = {}  # feature_id → resumen del último FEA (metadato)
        self.stackups: dict[str, dict] = {}  # cadenas de cotas con nombre (V7.3) → {eslabones, requisito}
        self.escenarios: dict[str, dict] = {}  # V8.3 D12: nombre → {escenario, resultado?} (services/escenarios)
        self.tensores, self.funciones = [], []  # puerta-de-publicacion D3 y D15: declarados
        self.justificadas: list[dict] = []  # puerta-sin-sobrediseno D6/D11: avisos y piezas justificados
        self.puerta_primera: dict = {}  # D9: el último comando del log en la PRIMERA corrida de la puerta
        self.ext: dict[str, dict] = {}  # datos de cada extensión (doc/ext_manifest.py, nucleo-abierto F1d)
        self.agent_notes: list[str] = []  # memoria de proyecto del agente IA
        self.regen_suppressed: list[dict] = []  # SUPRIMIDOS por una carga tolerante (transitorio, NUNCA al manifest; vacío si estricto)
        self.solo_lectura: dict | None = None  # D4: usa una extensión ausente (doc/solo_lectura.py, al cargar)
        self.electrico = carril.vacio()  # el carril evaluado (V8.1): derivado, nunca se guarda
        self._seq = 0
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._coalesce_key: str | None = None
        # caché de regen incremental: firma acumulada por comando + checkpoints (para reanudar)
        self._regen_sigs: list[str] = []
        self._regen_ckpts: dict[int, RegenState] = {}

    _UNDO_CAP = 50  # cota del historial de deshacer (los snapshots retienen la caché de regen)

    # ------------------------------------------------------------- estado
    def _snapshot(self) -> dict:
        # la caché de regen viaja en el snapshot (Fix C): al restaurar se repone ANTES de regenerar →
        # el rollback resume del último checkpoint (replay ~0) e inmune a un fallo repetido.
        solo_lectura.bloquear(self)  # D4: toda mutación del log y deshacer pasan por aquí
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
        (no bool) en el rango de los comandos de ESCENA y estado = `RegenState` con la escena
        dict. Cualquier anomalía → el caller fuerza replay completo en vez de reventar
        (blindaje Fix B). Las firmas (sigs) NO se validan: son strings y comparar con basura
        da False sin petar, y un largo distinto es NORMAL entre append y regenerate."""
        n = carril.n_escena(self.commands)
        try:
            for k, st in self._regen_ckpts.items():
                if isinstance(k, bool) or not isinstance(k, int) or not (0 <= k < n):
                    return False
                if not (isinstance(st, RegenState) and isinstance(st.scene, dict)):
                    return False
        except Exception:
            return False
        return True

    def _prune_or_raise(self, state: RegenState, tolerant: bool, suppressed: list) -> None:
        """Valida que juntas/mates/restricciones/fijadores/anclajes referencian entidades
        VIVAS. Estricto: lanza DocumentError al primer huérfano. Tolerante (solo en carga):
        ELIMINA la entidad huérfana del estado EN MEMORIA (el LOG jamás se toca) y la
        reporta en `suppressed`. Orden: juntas antes que restricciones (una restricción
        cuya junta se podó también queda huérfana)."""
        scene, joints, mates = state.scene, state.joints, state.mates
        constraints, fasteners, grounds = state.constraints, state.fasteners, state.grounds

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

        # 1) firma acumulada por comando de ESCENA (el carril va aparte: doc/carril.py)
        escena, lane, _ = carril.separar(self.commands)
        sigs, leen = carril.firmas(escena, lane), carril.antes_de_leer(escena)
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
            state = ckpts[resume].copy()
            new_ckpts = {i: st for i, st in ckpts.items() if i <= resume}
            start = resume + 1
        else:
            state = RegenState()
            new_ckpts = {}
            start = 0
        suppressed: list[dict] = []
        # 5) ejecutar solo la cola (desde el primer cambio) y capturar checkpoints
        last = len(escena) - 1
        for i in range(start, len(escena)):
            cmd = escena[i]
            try:
                execute_command(state, cmd["id"], cmd["type"], cmd["params"], self.attachments,
                                carril.lectura(cmd, lane))
            except CommandError as exc:
                if tolerant:
                    suppressed.append(
                        {"command_id": cmd["id"], "type": cmd["type"], "error": str(exc)}
                    )
                else:
                    raise DocumentError(
                        f"Error al regenerar {cmd['id']} ({cmd['type']}): {exc}"
                    ) from exc
            if i == last or i % self._REGEN_STRIDE == 0 or i in leen:  # A6: antes de leer
                new_ckpts[i] = state.copy()
        # 6) referencias colgando: estricto lanza, tolerante poda + reporta
        self._prune_or_raise(state, tolerant, suppressed)
        scene = state.scene
        try:
            solve_mates(scene, state.mates)
        except MateError as exc:
            if tolerant:
                suppressed.append({"command_id": None, "type": "mates", "error": str(exc)})
            else:
                raise DocumentError(f"Error al resolver los mates: {exc}") from exc
        # membresía de grupos: campo DERIVADO por command_id (integridad TOLERANTE —
        # un member cuyo comando desapareció se reporta vía missing_members, no falla)
        assign_feature_groups(scene, state.groups)
        for fid, feat in scene.items():
            feat.visible = fid not in self.hidden
            # .get con default: un executor puede haber seteado ya el material de la
            # pieza (insert_project importa los del proyecto origen) — no pisarlo. La pieza
            # gana a su comando (la raíz de un patrón: doc/por_comando.py)
            mat = de_la_pieza(fid, feat.command_id, self.materials, self.materiales_por_comando)
            if mat is not None:
                feat.material = mat
            # boceto-guía DERIVADO por command_id (como la membresía de grupos)
            feat.is_guide = feat.command_id in self.sketch_guides
        # variables resueltas en LOCAL (antes de tocar self: si truena, self intacto)
        try:
            variables_resolved = resolve_all(state.variables)
        except ExpressionError as exc:
            raise DocumentError(f"Error en las variables del proyecto: {exc}") from exc
        electrico = carril.evaluar(lane, scene, state.variables, variables_resolved, log=escena,
                                   tolerant=tolerant, suprimidos=suppressed, attachments=self.attachments)
        # 7) BLOQUE ÚNICO de asignaciones — a partir de aquí NADA puede lanzar (atomicidad)
        self.scene = scene
        self.joints = state.joints
        self.mates = state.mates
        self.constraints = state.constraints
        self.fasteners = state.fasteners
        self.grounds = state.grounds
        self.groups = state.groups
        self.variables_raw = state.variables
        self.variables_resolved = variables_resolved
        self.regen_suppressed = suppressed
        self.electrico = electrico
        self._regen_sigs = sigs
        self._regen_ckpts = new_ckpts

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

    def _push_undo(self, snap: dict, escena_antes, intencion=None, foco=None) -> None:
        """ÚNICO punto donde se apila un cambio: lo etiqueta (D1; D10: nunca lanza), acota el
        historial y limpia rehacer. `escena_antes` nombra lo que la mutación eliminó."""
        snap["etiqueta"] = _pasos.etiqueta(snap["commands"], self.commands, escena_antes,
                                           self.scene, intencion, foco)
        self._undo.append(snap)
        del self._undo[: -self._UNDO_CAP]  # acota el historial (snapshots retienen caché)
        self._redo.clear()
        self._coalesce_key = None

    def _mutate(self, fn, coalesce_key: str | None = None, intencion=None, foco=None) -> None:
        """Aplica un cambio al log con rollback automático si la regeneración falla.
        Mutaciones consecutivas con la misma coalesce_key (vista previa en vivo) comparten
        un único punto de deshacer, cuya etiqueta se recalcula contra él (D11)."""
        snap, escena = self._snapshot(), self.scene
        try:
            fn()
            self.regenerate()
            self._check_strict()
        except Exception:
            self._restore(snap)
            raise
        if coalesce_key and coalesce_key == self._coalesce_key and self._undo:
            snap = self._undo.pop()  # se re-apila el de arriba con su etiqueta recalculada
        self._push_undo(snap, escena, intencion, foco)
        self._coalesce_key = coalesce_key

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
        """Asigna cmd_id, incrementa seq e inserta el record (los 'vars' se hoist-ean al principio;
        el carril materializa su designación, V8.1 D3). NO valida ni regenera: execute(_many)."""
        params = sello.sellar(self, cmd_type, carril.materializar(self.commands, cmd_type, params))
        self._seq += 1
        cmd_id = f"c{self._seq}"
        # deshacer devuelve `seq` pero no `hidden` (D12): un id reciclado no nace oculto
        self.hidden -= {h for h in self.hidden if h == cmd_id or h.startswith(cmd_id + "_")}
        record = {"id": cmd_id, "type": cmd_type, "params": params}
        spec = REGISTRY.get(cmd_type)
        if spec is not None and spec.kind == "vars":
            self.commands.insert(self._vars_block_end(), record)
        else:
            self.commands.append(record)
        return cmd_id

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
        clone.materials, clone.vertical, clone.scene = dict(self.materials), self.vertical, self.scene
        clone.materiales_por_comando = dict(self.materiales_por_comando)
        clone.sketch_guides = set(self.sketch_guides)
        clone._regen_sigs = list(self._regen_sigs)
        clone._regen_ckpts = dict(self._regen_ckpts)  # comparte refs de shape OCCT (read-only)
        if actions:
            new_ids = clone.execute_many(actions)
        else:
            clone.regenerate()
            new_ids = []
        return clone.scene, new_ids

    # --------------------------------------------------------- undo / redo
    can_undo = property(lambda self: bool(self._undo))
    can_redo = property(lambda self: bool(self._redo))
    # etiquetas de cada pila, la más próxima primero
    undo_labels = property(lambda self: _pasos.etiquetas(self._undo))
    redo_labels = property(lambda self: _pasos.etiquetas(self._redo))

    def undo(self, pasos: int = 1) -> None:
        self._mover(self._undo, self._redo, pasos, "deshacer")

    def redo(self, pasos: int = 1) -> None:
        self._mover(self._redo, self._undo, pasos, "rehacer")

    def _mover(self, origen: list, destino: list, pasos: int, verbo: str) -> None:
        """Deshace (o rehace) `pasos` cambios con UN regenerate (D6), igual que `pasos` llamadas
        de a uno. Peek-then-commit (Fix C): las pilas no se tocan hasta que la restauración
        sobrevive (si revienta, se vuelve al estado actual). `hidden` no se toca (D12)."""
        error = _pasos.error_de_pasos(pasos, len(origen), verbo)
        if error:
            raise DocumentError(error)
        actual = self._snapshot()
        try:
            self._restore({**origen[-pasos], "hidden": self.hidden})
        except Exception:
            try:
                self._restore(actual)
            except Exception:
                pass
            raise
        origen[:], destino[:] = _pasos.trasladar(origen, destino, pasos, actual, self._UNDO_CAP)
        self._coalesce_key = None
