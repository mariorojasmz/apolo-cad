import { create } from "zustand";
import { api, connectWs } from "../api";
import { reportError } from "../errorlog";
import type {
  CatalogItem, ChatAction, ChatMsg, CommandSchema, ConnectivityOut, DropResult, FeatureOut, GravityResult,
  KinematicsOut, MateRow, MotionKeyframe, MotionStudy, RailConstraint, SceneOut,
} from "../types";

const NO_FEATURES: FeatureOut[] = [];

// throttle del solver de restricciones de riel mientras se arrastra un driver
let solveTimer: number | null = null;

/** Selector estable: nunca devuelve un array recién creado (evita bucles de render). */
export const selectFeatures = (s: { scene: SceneOut | null }): FeatureOut[] =>
  s.scene?.features ?? NO_FEATURES;

interface AppState {
  schemas: CommandSchema[];
  scene: SceneOut | null;
  catalog: CatalogItem[];
  selection: string[];
  dialogSchema: CommandSchema | null;
  showVariables: boolean;
  showLibrary: boolean;
  showDrawing: boolean;
  showHome: boolean;
  sketcherOpen: boolean;
  sketcherInitial: { commandId: string; type: string; params: Record<string, unknown> } | null;
  dockPanels: string[]; // ids de paneles presentes en el layout de Dockview (resaltado de StatusBar)
  kinematics: KinematicsOut | null;
  constraints: RailConstraint[];
  mates: MateRow[];
  motionStudies: MotionStudy[];
  activeStudy: string | null;
  jointValues: Record<string, number>;
  physicsResult: DropResult | null;
  physicsPlaying: boolean;
  physicsSpeed: number;
  physicsToken: number;
  gravityResult: GravityResult | null;  // caída de la máquina animada en el viewport (mallas reales)
  gravityPlaying: boolean;
  gravitySpeed: number;
  gravityToken: number;
  connectivity: ConnectivityOut | null;  // uniones declaradas (fijadores + anclajes a tierra)
  contextMenu: { x: number; y: number; targetId: string | null } | null;
  showShortcuts: boolean;
  pickRequest: ((point: [number, number, number]) => void) | null;
  error: string | null;
  busy: boolean;
  busyLabel: string | null;
  blocking: boolean;
  chat: ChatMsg[];
  chatBusy: boolean;

  init: () => Promise<void>;
  refresh: () => Promise<void>;
  select: (ids: string[]) => void;
  toggleSelect: (id: string) => void;
  openDialog: (schema: CommandSchema | null) => void;
  openVariables: (open: boolean) => void;
  openLibrary: (open: boolean) => void;
  openDrawing: (open: boolean) => void;
  openHome: (open: boolean) => void;
  adoptScene: (scene: SceneOut) => void;
  openSketcher: (initial?: { commandId: string; type: string; params: Record<string, unknown> }) => void;
  closeSketcher: () => void;
  setDockPanels: (ids: string[]) => void;
  refreshKinematics: () => Promise<void>;
  setJointValue: (name: string, value: number) => void;
  driveJoint: (name: string, value: number) => void;
  setJointValues: (values: Record<string, number>) => void;
  resetJointValues: () => void;
  deleteJoint: (name: string) => Promise<void>;
  refreshMotion: () => Promise<void>;
  saveMotion: (name: string, keyframes: MotionKeyframe[]) => Promise<void>;
  deleteStudy: (name: string) => Promise<void>;
  setActiveStudy: (name: string | null) => void;
  setPhysicsResult: (result: DropResult | null) => void;
  setPhysicsPlaying: (playing: boolean) => void;
  setPhysicsSpeed: (speed: number) => void;
  clearPhysics: () => void;
  setGravityResult: (result: GravityResult | null) => void;
  setGravityPlaying: (playing: boolean) => void;
  setGravitySpeed: (speed: number) => void;
  clearGravity: () => void;
  refreshConnectivity: () => Promise<void>;
  declareStructure: () => Promise<void>;
  deleteFastener: (name: string) => Promise<void>;
  deleteGround: (name: string) => Promise<void>;
  groundSelection: () => Promise<void>;
  fastenSelection: () => Promise<void>;
  refreshMates: () => Promise<void>;
  deleteMate: (name: string) => Promise<void>;
  requestPick: (cb: ((point: [number, number, number]) => void) | null) => void;
  importStep: (file: File, split: boolean) => Promise<void>;
  setError: (msg: string | null) => void;

  runCommand: (type: string, params: Record<string, unknown>) => Promise<boolean>;
  editCommand: (id: string, params: Record<string, unknown>, transient?: boolean, merge?: boolean) => Promise<boolean>;
  // Variantes SILENCIOSAS para manipulación directa (estirar/rotar/mover): sin barra global de carga
  // (`busy`), serializadas/coalescidas en una cola de fondo → fluidas, sin pisarse. `syncing` = # en
  // vuelo. `blockedIds` = piezas cuyo guardado FALLÓ (bloqueadas: tinte rojo + no manipulables hasta
  // que el auto-reintento las guarde). `retryBlocked` reintenta ya (manual).
  syncing: number;
  blockedIds: string[];
  runCommandSilent: (type: string, params: Record<string, unknown>) => Promise<boolean>;
  editCommandSilent: (id: string, params: Record<string, unknown>, merge?: boolean) => Promise<boolean>;
  retryBlocked: (id: string) => void;
  saveVariable: (name: string, expression: string) => Promise<boolean>;
  deleteVariable: (name: string) => Promise<boolean>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  toggleVisibility: (id: string) => Promise<void>;
  toggleGuide: (ids?: string[]) => Promise<void>;
  newGuideBox: () => Promise<void>;
  newProject: () => Promise<void>;
  openProject: (file: File) => Promise<void>;
  openProjectById: (id: number) => Promise<void>;
  createProject: (name: string, template: string | null) => Promise<void>;
  duplicateProject: (id: number) => Promise<void>;
  deleteProject: (id: number) => Promise<void>;
  saveRevision: (note: string) => Promise<void>;
  restoreRevision: (id: number) => Promise<void>;
  /** Envuelve cualquier promesa con el indicador global de carga (para componentes que llaman api.* directo). */
  runTracked: <T>(label: string, fn: () => Promise<T>, opts?: { blocking?: boolean }) => Promise<T | null>;

  // ergonomía "CAD pro"
  clearSelection: () => void;
  selectAll: () => void;
  deleteSelection: () => Promise<void>;
  duplicateSelection: () => Promise<void>;
  nudgeSelection: (dx: number, dy: number, dz: number) => Promise<void>;
  bulkVisibility: (ids: string[], visible: boolean) => Promise<void>;
  hideSelection: () => Promise<void>;
  isolate: (ids?: string[]) => Promise<void>;
  showAll: () => Promise<void>;
  openContextMenu: (cm: { x: number; y: number; targetId: string | null } | null) => void;
  toggleShortcuts: (open?: boolean) => void;

  // Boceto de masas — snapping del gizmo (Fase 2)
  snapEnabled: boolean;
  snapStep: number;
  toggleSnap: () => void;
  setSnapStep: (n: number) => void;

  // Boceto de masas — primitivas + fusión (Fase 3C)
  newPrimitive: (kind: "box" | "cylinder") => Promise<void>; // 3C soltar primitiva real
  fuseSelection: () => Promise<void>; // 3C fusión booleana con guarda de conectividad

  autoMode: boolean;
  setAutoMode: (on: boolean) => void;
  sendChat: (text: string) => Promise<void>;
  resolveActions: (msgIndex: number, accept: boolean) => Promise<void>;
}

// Texto amistoso para el indicador de carga, derivado del prefijo de la etiqueta técnica
// (la etiqueta técnica se conserva intacta para el log de errores). Fuente ÚNICA del
// "qué está pasando" que ven el badge de la barra de estado y el overlay bloqueante.
const BUSY_TEXT: Record<string, string> = {
  runCommand: "Ejecutando comando…",
  editCommand: "Aplicando cambio…",
  setVariable: "Regenerando modelo…",
  deleteVariable: "Regenerando modelo…",
  guide: "Marcando boceto…",
  undo: "Deshaciendo…",
  redo: "Rehaciendo…",
  importStep: "Importando STEP…",
  openProject: "Abriendo proyecto…",
  openProjectById: "Abriendo proyecto…",
  newProject: "Creando proyecto…",
  createProject: "Creando proyecto…",
  restoreRevision: "Restaurando revisión…",
  duplicateProject: "Duplicando proyecto…",
  deleteProject: "Eliminando proyecto…",
  saveRevision: "Guardando revisión…",
  applyConfiguration: "Aplicando configuración…",
  saveConfiguration: "Guardando configuración…",
  deleteConfiguration: "Eliminando configuración…",
  deleteSelection: "Eliminando…",
  duplicateSelection: "Duplicando…",
  nudgeSelection: "Moviendo…",
  bulkVisibility: "Actualizando visibilidad…",
  visibility: "Actualizando visibilidad…",
  deleteJoint: "Eliminando junta…",
  deleteMate: "Eliminando unión…",
  declareStructure: "Auto-declarando estructura…",
  deleteFastener: "Eliminando unión…",
  deleteGround: "Eliminando anclaje…",
  acceptActions: "Aplicando acciones…",
  checks: "Comprobando…",
  drop: "Simulando…",
  scanMotion: "Comprobando recorrido…",
  bom: "Cargando lista de materiales…",
  mates: "Cargando ensamblaje…",
  drawing: "Generando plano…",
  save_reqs: "Guardando requisitos…",
  costing: "Calculando costos…",
};
const busyText = (label: string): string => BUSY_TEXT[label.split(":")[0]] ?? "Trabajando…";

// Contadores de operaciones en curso (la store es instancia única → estado de módulo aislado y
// seguro). El CONTADOR evita el bug del booleano: que una operación que termina apague el
// indicador mientras otra sigue corriendo (awaits solapados).
let pendingCount = 0;
let blockingCount = 0;

type GuardOpts = { label?: string; blocking?: boolean };

async function guard<T>(
  set: (s: Partial<AppState>) => void,
  fn: () => Promise<T>,
  labelOrOpts: string | GuardOpts = "acción",
): Promise<T | null> {
  const opts: GuardOpts = typeof labelOrOpts === "string" ? { label: labelOrOpts } : labelOrOpts;
  const label = opts.label ?? "acción";
  pendingCount++;
  if (opts.blocking) blockingCount++;
  set({ busy: true, busyLabel: busyText(label), blocking: blockingCount > 0, error: null });
  try {
    return await fn();
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    set({ error: message });
    reportError("action", message, { action: label });
    return null;
  } finally {
    pendingCount = Math.max(0, pendingCount - 1);
    if (opts.blocking) blockingCount = Math.max(0, blockingCount - 1);
    if (pendingCount === 0) {
      blockingCount = 0;
      set({ busy: false, busyLabel: null, blocking: false });
    } else {
      set({ blocking: blockingCount > 0 });
    }
  }
}

// Sincronización de FONDO para manipulación directa: sin barra global (`busy`), el preview optimista
// del viewport ya muestra el resultado. `syncing` cuenta las operaciones en vuelo.
type SetFn = (s: Partial<AppState>) => void;
let syncingCount = 0;

/** Reintenta ante fallo TRANSITORIO (red/servidor ocupado) antes de rendirse. */
async function withRetry<T>(run: () => Promise<T>, tries = 2, delayMs = 350): Promise<T> {
  try {
    return await run();
  } catch (e) {
    if (tries > 0) { await new Promise((r) => setTimeout(r, delayMs)); return withRetry(run, tries - 1, delayMs); }
    throw e;
  }
}

// COALESCING de ediciones por command_id: mientras se guarda una caja, las siguientes ediciones NO se
// encolan una a una; se guarda solo la ÚLTIMA (los estados intermedios de un arrastre no importan) →
// la cola queda ACOTADA (máx. 1 en vuelo + 1 pendiente por pieza), sin bloquear al usuario ni crecer.
const editPending = new Map<string, { params: Record<string, unknown>; merge: boolean }>();
const editInFlight = new Set<string>();
const editDrain = new Map<string, { p: Promise<boolean>; resolve: (b: boolean) => void }>();
// Última edición ENCOLADA por command_id (viva mientras haya cola/vuelo; se limpia al drenar con éxito).
// Fuente FRESCA de params para commits encadenados: durante estirones rápidos el coalescing suprime las
// escenas intermedias → st.scene queda RETRASADO; leer de ahí ancla el siguiente commit a params viejos.
const lastQueuedEdit = new Map<string, Record<string, unknown>>();
/** Params de la última edición silenciosa aún sin drenar para `id` (undefined si no hay). */
export function queuedEditParams(id: string): Record<string, unknown> | undefined {
  return lastQueuedEdit.get(id);
}
let wsRefreshTimer: ReturnType<typeof setTimeout> | null = null; // debounce del refresh por WebSocket

// BLOQUEO como ÚLTIMO RECURSO: si un guardado FALLA (tras los reintentos inmediatos) la pieza queda
// bloqueada (tinte rojo + no manipulable) con AUTO-REINTENTO de backoff creciente; al recuperarse se
// desbloquea. `blockedInfo` guarda el reintento + su timer por id.
const blockedInfo = new Map<string, { retry: () => void; timer: number; delay: number }>();
function markBlocked(set: SetFn, id: string, retry: () => void): void {
  const prev = blockedInfo.get(id);
  if (prev) clearTimeout(prev.timer);
  const delay = Math.min(prev ? prev.delay * 2 : 2000, 30000); // backoff 2s→30s
  const timer = window.setTimeout(retry, delay);
  blockedInfo.set(id, { retry, timer, delay });
  set({ blockedIds: [...blockedInfo.keys()] });
}
function unblock(set: SetFn, id: string): void {
  const b = blockedInfo.get(id);
  if (!b) return;
  clearTimeout(b.timer);
  blockedInfo.delete(id);
  set({ blockedIds: [...blockedInfo.keys()] });
}

function pumpEdit(set: SetFn, id: string): void {
  if (editInFlight.has(id) || !editPending.has(id)) return;
  editInFlight.add(id);
  syncingCount++; set({ syncing: syncingCount });
  const next = editPending.get(id)!;
  editPending.delete(id);
  let respScene: SceneOut | null = null; // escena de ESTA respuesta; solo se aplica si es la ÚLTIMA
  void withRetry(() => api.editCommand(id, next.params, false, next.merge))
    .then((scene) => { respScene = scene ?? null; return true; })
    .catch((e) => { const m = e instanceof Error ? e.message : String(e); set({ error: `No se pudo guardar; reintentando… (${m})` }); reportError("action", m, { action: "sync" }); return false; })
    .then((ok) => {
      syncingCount = Math.max(0, syncingCount - 1); set({ syncing: syncingCount });
      editInFlight.delete(id);
      // Aplica la escena del servidor SOLO si NO hay una edición MÁS NUEVA en cola: si la hay, esta
      // respuesta es de un tamaño INTERMEDIO/viejo → aplicarla haría PARPADEAR el preview a ese tamaño
      // antes de llegar al final. El preview optimista se mantiene hasta la respuesta ÚLTIMA (cola drenada).
      if (ok && respScene && !editPending.has(id)) set({ scene: respScene });
      if (ok && !editPending.has(id)) lastQueuedEdit.delete(id); // drenado: st.scene vuelve a ser la fuente
      if (ok) unblock(set, id); // guardó bien → desbloquea (si estaba bloqueada)
      else markBlocked(set, id, () => { editPending.set(id, next); pumpEdit(set, id); }); // falló → bloquea + auto-reintento
      if (editPending.has(id)) pumpEdit(set, id); // llegó una edición más nueva → guárdala
      else { const d = editDrain.get(id); editDrain.delete(id); d?.resolve(ok); } // cola de la pieza DRENADA
    });
}

// Cola serializada (para transforms: rotar/mover/subir-Z, que son deltas y no se pueden coalescer).
let syncTail: Promise<unknown> = Promise.resolve();
function enqueueSilent(set: SetFn, id: string, run: () => Promise<SceneOut>): Promise<boolean> {
  const p = syncTail.then(async () => {
    syncingCount++;
    set({ syncing: syncingCount });
    try {
      const scene = await withRetry(run);
      if (scene) set({ scene });
      if (id) unblock(set, id);
      return scene !== null;
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      set({ error: `No se pudo guardar; reintentando… (${message})` });
      reportError("action", message, { action: "sync" });
      if (id) markBlocked(set, id, () => { void enqueueSilent(set, id, run); }); // falló → bloquea + auto-reintento
      return false;
    } finally {
      syncingCount = Math.max(0, syncingCount - 1);
      set({ syncing: syncingCount });
    }
  });
  syncTail = p.catch(() => false);
  return p;
}

export const useStore = create<AppState>((set, get) => ({
  schemas: [],
  scene: null,
  catalog: [],
  selection: [],
  dialogSchema: null,
  showVariables: false,
  showLibrary: false,
  showDrawing: false,
  showHome: false,
  sketcherOpen: false,
  sketcherInitial: null,
  dockPanels: [],
  kinematics: null,
  constraints: [],
  mates: [],
  motionStudies: [],
  activeStudy: null,
  jointValues: {},
  physicsResult: null,
  physicsPlaying: false,
  physicsSpeed: 1.0,
  physicsToken: 0,
  gravityResult: null,
  gravityPlaying: false,
  gravitySpeed: 1.0,
  gravityToken: 0,
  connectivity: null,
  contextMenu: null,
  showShortcuts: false,
  pickRequest: null,
  error: null,
  busy: false,
  busyLabel: null,
  blocking: false,
  chat: [],
  chatBusy: false,
  autoMode: false,
  snapEnabled: false, // "Pegar" (imán) apagado por defecto — se activa a propósito (F4A/F4D)
  snapStep: 10,

  init: async () => {
    const [schemas, scene, catalog] = await Promise.all([api.schemas(), api.scene(), api.catalog()]);
    set({ schemas, scene, catalog });
    void get().refreshKinematics();
    connectWs(() => {
      // `document_changed` llega por CADA comando del servidor — INCLUIDOS los nuestros. Refrescar por
      // cada evento reproduciría cada tamaño intermedio (PARPADEO) durante la manipulación directa.
      // Debounce + gate: espera a que se calme y NO refresques si aún hay ediciones silenciosas propias
      // en vuelo (su respuesta ya trae la escena final autoritativa). Solo refresca por cambios EXTERNOS
      // (agente/MCP/otro cliente) una vez que todo está quieto.
      if (wsRefreshTimer) clearTimeout(wsRefreshTimer);
      wsRefreshTimer = setTimeout(() => {
        wsRefreshTimer = null;
        const s = get();
        if (s.busy || s.syncing > 0) return; // ocupados con lo nuestro → nuestra propia respuesta cierra el estado
        void s.refresh();
      }, 250);
    });
  },

  refresh: async () => {
    const scene = await api.scene();
    const valid = new Set(scene.features.map((f) => f.id));
    set({ scene, selection: get().selection.filter((id) => valid.has(id)) });
    get().clearPhysics(); // el modelo cambió → las cajas soltadas dejan de ser válidas
    get().clearGravity();
    void get().refreshKinematics();
  },

  refreshKinematics: async () => {
    try {
      const [kinematics, constraints] = await Promise.all([api.kinematics(), api.constraints()]);
      const names = new Set(kinematics.joints.map((j) => j.name));
      const values = Object.fromEntries(
        Object.entries(get().jointValues).filter(([name]) => names.has(name)),
      );
      set({ kinematics, constraints, jointValues: values });
    } catch {
      /* sin cinemática disponible */
    }
  },

  setJointValue: (name, value) => set({ jointValues: { ...get().jointValues, [name]: value } }),

  // Mueve un driver y RESUELVE las juntas dependientes (restricción de riel) en
  // vivo. El feedback es inmediato (set local); el solve va con throttle ligero
  // para no saturar el endpoint mientras se arrastra el slider.
  driveJoint: (name, value) => {
    set({ jointValues: { ...get().jointValues, [name]: value } });
    if (get().constraints.length === 0) return;
    if (solveTimer !== null) clearTimeout(solveTimer);
    solveTimer = window.setTimeout(() => {
      solveTimer = null;
      const current = get().jointValues;
      void api
        .solveConstraints(current)
        .then((r) => set({ jointValues: { ...get().jointValues, ...r.values } }))
        .catch(() => {});
    }, 40);
  },

  setJointValues: (values) => set({ jointValues: values }),
  resetJointValues: () => set({ jointValues: {} }),

  refreshMotion: async () => {
    try {
      const studies = (await api.motion()).studies;
      const active = get().activeStudy;
      set({
        motionStudies: studies,
        activeStudy: studies.some((s) => s.name === active)
          ? active
          : studies[0]?.name ?? null,
      });
    } catch {
      /* sin motion disponible */
    }
  },
  saveMotion: async (name, keyframes) => {
    try {
      const studies = (await api.saveMotion(name, keyframes)).studies;
      set({ motionStudies: studies, activeStudy: studies.some((s) => s.name === name) ? name : get().activeStudy });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },
  deleteStudy: async (name) => {
    try {
      const studies = (await api.deleteMotionStudy(name)).studies;
      const active = get().activeStudy;
      set({
        motionStudies: studies,
        activeStudy: active === name ? (studies[0]?.name ?? null) : active,
      });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },
  setActiveStudy: (name) => set({ activeStudy: name }),

  // Física (drop-test): estado efímero, NO persiste. El token++ dispara el rebuild
  // de las cajas en el viewport (patrón overlay efímero).
  setPhysicsResult: (result) =>
    set({ physicsResult: result, physicsPlaying: !!result, physicsToken: get().physicsToken + 1 }),
  setPhysicsPlaying: (playing) => set({ physicsPlaying: playing }),
  setPhysicsSpeed: (speed) => set({ physicsSpeed: speed }),
  clearPhysics: () =>
    set({ physicsResult: null, physicsPlaying: false, physicsToken: get().physicsToken + 1 }),

  // Gravedad de la máquina: anima las MALLAS REALES en el viewport (no overlay). Efímero,
  // NO persiste. token++ dispara el rebuild del animador; clearGravity restaura las mallas.
  setGravityResult: (result) =>
    set({ gravityResult: result, gravityPlaying: !!result, gravityToken: get().gravityToken + 1 }),
  setGravityPlaying: (playing) => set({ gravityPlaying: playing }),
  setGravitySpeed: (speed) => set({ gravitySpeed: speed }),
  clearGravity: () =>
    set({ gravityResult: null, gravityPlaying: false, gravityToken: get().gravityToken + 1 }),

  requestPick: (cb) => set({ pickRequest: cb }),

  importStep: async (file, split) => {
    const scene = await guard(set, () => api.importStep(file, split), { label: "importStep", blocking: true });
    if (scene) set({ scene });
  },

  deleteJoint: async (name) => {
    const scene = await guard(set, () => api.deleteJoint(name), `deleteJoint:${name}`);
    if (scene) {
      set({ scene });
      void get().refreshKinematics();
    }
  },

  refreshMates: async () => {
    try {
      set({ mates: await api.mates() });
    } catch {
      /* sin mates disponibles */
    }
  },

  deleteMate: async (name) => {
    const scene = await guard(set, () => api.deleteMate(name), `deleteMate:${name}`);
    if (scene) {
      set({ scene });
      void get().refreshMates();
    }
  },

  // ---- conectividad de ensamblaje (uniones declaradas) ----
  refreshConnectivity: async () => {
    try {
      set({ connectivity: await api.connectivity() });
    } catch {
      /* sin conectividad disponible */
    }
  },
  declareStructure: async () => {
    const scene = await guard(set, () => api.declareStructure(), "declareStructure");
    if (scene) {
      set({ scene });
      void get().refreshConnectivity();
      void get().refreshKinematics();
    }
  },
  deleteFastener: async (name) => {
    const scene = await guard(set, () => api.deleteFastener(name), `deleteFastener:${name}`);
    if (scene) {
      set({ scene });
      void get().refreshConnectivity();
    }
  },
  deleteGround: async (name) => {
    const scene = await guard(set, () => api.deleteGround(name), `deleteGround:${name}`);
    if (scene) {
      set({ scene });
      void get().refreshConnectivity();
    }
  },
  groundSelection: async () => {
    const ids = get().selection;
    if (ids.length !== 1) return;
    const ok = await get().runCommand("ground", { name: `g${Date.now()}`, feature: ids[0] });
    if (ok) void get().refreshConnectivity();
  },
  fastenSelection: async () => {
    const ids = get().selection;
    if (ids.length !== 2) return;
    const ok = await get().runCommand("fasten", { name: `f${Date.now()}`, a: ids[0], b: ids[1], kind: "perno" });
    if (ok) void get().refreshConnectivity();
  },

  select: (ids) => set({ selection: ids }),
  toggleSelect: (id) => {
    const current = get().selection;
    set({
      selection: current.includes(id) ? current.filter((s) => s !== id) : [...current, id],
    });
  },

  // ---- ergonomía "CAD pro" ----
  clearSelection: () => set({ selection: [] }),
  selectAll: () => set({ selection: (get().scene?.features ?? []).filter((f) => f.visible).map((f) => f.id) }),
  openContextMenu: (cm) => set({ contextMenu: cm }),
  toggleShortcuts: (open) => set({ showShortcuts: open ?? !get().showShortcuts }),

  bulkVisibility: async (ids, visible) => {
    if (!ids.length) return;
    const scene = await guard(set, () => api.bulkVisibility(ids, visible), "bulkVisibility");
    if (scene) set({ scene });
  },
  hideSelection: async () => {
    await get().bulkVisibility(get().selection, false);
  },
  isolate: async (ids) => {
    const keep = new Set(ids ?? get().selection);
    if (!keep.size) return;
    const hide = (get().scene?.features ?? []).filter((f) => f.visible && !keep.has(f.id)).map((f) => f.id);
    await get().bulkVisibility(hide, false);
  },
  showAll: async () => {
    const hidden = (get().scene?.features ?? []).filter((f) => !f.visible).map((f) => f.id);
    await get().bulkVisibility(hidden, true);
  },
  deleteSelection: async () => {
    const ids = get().selection;
    if (!ids.length) return;
    const actions = ids.map((id) => ({ type: "delete_feature", params: { feature: id } }));
    const scene = await guard(set, () => api.runBatch(actions), "deleteSelection");
    if (scene) {
      set({ scene, selection: [] });
      void get().refreshKinematics();
    }
  },
  duplicateSelection: async () => {
    const ids = get().selection;
    if (!ids.length) return;
    const actions = ids.map((id) => ({ type: "duplicate_feature", params: { feature: id } }));
    const scene = await guard(set, () => api.runBatch(actions), "duplicateSelection");
    if (scene) {
      set({ scene });
      void get().refreshKinematics();
    }
  },
  nudgeSelection: async (dx, dy, dz) => {
    const ids = get().selection;
    if (!ids.length) return;
    const t = { x: dx, y: dy, z: dz };
    const actions = ids.map((id) => ({ type: "transform", params: { feature: id, translate: t } }));
    const scene = await guard(set, () => api.runBatch(actions), "nudgeSelection");
    if (scene) {
      set({ scene });
      void get().refreshKinematics();
    }
  },
  openDialog: (schema) => set({ dialogSchema: schema }),
  openVariables: (open) => set({ showVariables: open }),
  openLibrary: (open) => set({ showLibrary: open }),
  openDrawing: (open) => set({ showDrawing: open }),
  openHome: (open) => set({ showHome: open }),
  openSketcher: (initial) => set({ sketcherOpen: true, sketcherInitial: initial ?? null }),
  closeSketcher: () => set({ sketcherOpen: false, sketcherInitial: null }),

  /** Adopta una escena venida de abrir/crear/restaurar proyecto. */
  adoptScene: (scene) => {
    set({ scene, selection: [], chat: [], jointValues: {}, showHome: false });
    get().clearPhysics();
    get().clearGravity();
    void get().refreshKinematics();
  },
  setDockPanels: (ids) => set({ dockPanels: ids }),
  setError: (msg) => set({ error: msg }),

  runCommand: async (type, params) => {
    const scene = await guard(set, () => api.runCommand(type, params), `runCommand:${type}`);
    if (scene) {
      set({ scene, dialogSchema: null });
      void get().refreshKinematics();
    }
    return scene !== null;
  },

  editCommand: async (id, params, transient = false, merge = false) => {
    const scene = await guard(
      set,
      () => api.editCommand(id, params, transient, merge),
      `editCommand:${id}${transient ? ":live" : ""}`,
    );
    if (scene) set({ scene });
    return scene !== null;
  },

  syncing: 0,
  blockedIds: [],
  runCommandSilent: (type, params) => enqueueSilent(set, String(params.feature ?? ""), () => api.runCommand(type, params)),
  editCommandSilent: (id, params, merge = false) => {
    editPending.set(id, { params, merge }); // el ÚLTIMO gana (coalescing)
    lastQueuedEdit.set(id, params); // fuente fresca para el SIGUIENTE commit (st.scene se retrasa)
    let d = editDrain.get(id);
    if (!d) { let resolve!: (b: boolean) => void; const p = new Promise<boolean>((r) => (resolve = r)); d = { p, resolve }; editDrain.set(id, d); }
    pumpEdit(set, id);
    return d.p; // resuelve cuando la cola de esta pieza DRENA (para el tinte "guardando")
  },
  retryBlocked: (id) => { const b = blockedInfo.get(id); if (b) { clearTimeout(b.timer); b.retry(); } },

  saveVariable: async (name, expression) => {
    const scene = await guard(set, () => api.setVariable(name, expression), `setVariable:${name}`);
    if (scene) set({ scene });
    return scene !== null;
  },

  deleteVariable: async (name) => {
    const scene = await guard(set, () => api.deleteVariable(name), `deleteVariable:${name}`);
    if (scene) set({ scene });
    return scene !== null;
  },

  undo: async () => {
    const scene = await guard(set, () => api.undo(), "undo");
    if (scene) {
      set({ scene });
      void get().refreshKinematics();
    }
  },
  redo: async () => {
    const scene = await guard(set, () => api.redo(), "redo");
    if (scene) {
      set({ scene });
      void get().refreshKinematics();
    }
  },

  toggleVisibility: async (id) => {
    const feat = get().scene?.features.find((f) => f.id === id);
    if (!feat) return;
    const scene = await guard(set, () => api.setVisibility(id, !feat.visible), `visibility:${id}`);
    if (scene) set({ scene });
  },

  toggleGuide: async (ids) => {
    const feats = get().scene?.features ?? [];
    const targets = ids ?? get().selection;
    if (!targets.length) return;
    // si TODOS ya son boceto → desmarcar (convertir en pieza real); si no → marcar todos
    const guide = !targets.every((id) => feats.find((f) => f.id === id)?.is_guide);
    let scene = null;
    for (const id of targets) {
      scene = await guard(set, () => api.setSketchGuide(id, guide), `guide:${id}`);
    }
    if (scene) set({ scene });
  },

  newGuideBox: async () => {
    const before = new Set((get().scene?.features ?? []).map((f) => f.id));
    const ok = await get().runCommand("create_box", { name: "Boceto", width: 200, depth: 200, height: 200 });
    if (!ok) return;
    const created = (get().scene?.features ?? []).filter((f) => !before.has(f.id)).map((f) => f.id);
    let scene = null;
    for (const id of created) {
      scene = await guard(set, () => api.setSketchGuide(id, true), `guide:${id}`);
    }
    if (created.length) set({ ...(scene ? { scene } : {}), selection: created });
  },

  // 3C: suelta una primitiva REAL (no guía) y la selecciona para colocarla con gizmo+snap
  newPrimitive: async (kind) => {
    const type = kind === "cylinder" ? "create_cylinder" : "create_box";
    const params = kind === "cylinder"
      ? { name: "Cilindro", radius: 60, height: 200 }
      : { name: "Bloque", width: 200, depth: 200, height: 200 };
    const before = new Set((get().scene?.features ?? []).map((f) => f.id));
    const ok = await get().runCommand(type, params);
    if (!ok) return;
    const created = (get().scene?.features ?? []).filter((f) => !before.has(f.id)).map((f) => f.id);
    if (created.length) set({ selection: created });
  },

  // 3C: fusión booleana (union) de la selección. GUARDA: boolean_op consume ids y reasigna
  // el resultado → rompería juntas/mates/fasteners/grounds; se BLOQUEA si alguna pieza los tiene.
  fuseSelection: async () => {
    const sel = get().selection;
    if (sel.length < 2) {
      set({ error: "Selecciona 2 o más sólidos que se solapen para fusionar." });
      return;
    }
    // refresca conectividad/uniones para que la guarda sea fiable
    await get().refreshMates();
    await get().refreshConnectivity();
    const st = get();
    const referenced = new Set<string>();
    for (const m of st.mates) { referenced.add(m.feature_a); referenced.add(m.feature_b); }
    for (const f of st.connectivity?.fasteners ?? []) { referenced.add(f.a); referenced.add(f.b); }
    for (const g of st.connectivity?.grounds ?? []) referenced.add(g.feature);
    for (const j of st.kinematics?.joints ?? []) { referenced.add(j.parent); referenced.add(j.child); }
    const blocked = sel.filter((id) => referenced.has(id));
    if (blocked.length) {
      set({
        error:
          "No se puede fusionar: alguna pieza tiene uniones declaradas (juntas/mates/fasteners). " +
          "Fusionar rompería esas referencias — quítalas primero, o fusiona piezas sin conectividad.",
      });
      return;
    }
    const ok = await get().runCommand("boolean_op", {
      operation: "union", target: sel[0], tools: sel.slice(1), name: "Fusión",
    });
    if (ok) set({ selection: [] });
  },

  newProject: async () => {
    const scene = await guard(set, () => api.newProject("Sin título"), { label: "newProject", blocking: true });
    if (scene) {
      set({ scene, selection: [], chat: [] });
      get().clearPhysics();
      get().clearGravity();
    }
  },

  openProject: async (file) => {
    const scene = await guard(set, () => api.openProject(file), { label: "openProject", blocking: true });
    if (scene) {
      set({ scene, selection: [] });
      get().clearPhysics();
      get().clearGravity();
    }
  },

  // Operaciones de proyecto pesadas (reemplazan la escena) → bloqueantes; alimentan el
  // overlay global y simplifican HomeScreen (antes tenía su propio `busy` local duplicado).
  openProjectById: async (id) => {
    const scene = await guard(set, () => api.openProjectById(id), { label: "openProjectById", blocking: true });
    if (scene) get().adoptScene(scene);
  },
  createProject: async (name, template) => {
    const scene = await guard(set, () => api.createProject(name, template), { label: "createProject", blocking: true });
    if (scene) get().adoptScene(scene);
  },
  duplicateProject: async (id) => {
    await guard(set, () => api.duplicateProject(id), { label: "duplicateProject", blocking: true });
  },
  deleteProject: async (id) => {
    await guard(set, () => api.deleteProject(id), "deleteProject");
  },
  saveRevision: async (note) => {
    await guard(set, () => api.saveRevision(note), "saveRevision");
  },
  restoreRevision: async (id) => {
    const scene = await guard(set, () => api.restoreRevision(id), { label: "restoreRevision", blocking: true });
    if (scene) get().adoptScene(scene);
  },
  runTracked: (label, fn, opts) => guard(set, fn, { label, blocking: opts?.blocking }),

  setAutoMode: (on) => set({ autoMode: on }),

  toggleSnap: () => set((s) => ({ snapEnabled: !s.snapEnabled })),
  setSnapStep: (n) => set({ snapStep: Number.isFinite(n) && n > 0 ? n : 1 }),

  sendChat: async (text) => {
    const history = get().chat.filter((m) => m.content.trim() !== "");
    const messages = [...history.map((m) => ({ role: m.role, content: m.content })), { role: "user", content: text }];
    const auto = get().autoMode;
    set({
      chat: [...get().chat, { role: "user", content: text }, { role: "assistant", content: "" }],
      chatBusy: true,
    });

    const patchLast = (patch: Partial<ChatMsg>) => {
      const chat = [...get().chat];
      chat[chat.length - 1] = { ...chat[chat.length - 1], ...patch };
      set({ chat });
    };

    try {
      const res = await api.chat(messages, auto);
      if (!res.ok || !res.body) throw new Error(`Error ${res.status} del servidor`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const frame = buffer.slice(0, idx).trim();
          buffer = buffer.slice(idx + 2);
          if (!frame.startsWith("data:")) continue;
          const event = JSON.parse(frame.slice(5).trim());
          if (event.type === "text") {
            patchLast({ content: get().chat[get().chat.length - 1].content + event.text });
          } else if (event.type === "tool") {
            const last = get().chat[get().chat.length - 1];
            patchLast({ tools: [...(last.tools ?? []), event.name as string] });
          } else if (event.type === "actions") {
            if (event.executed) {
              // modo autónomo: el lote ya se ejecutó; refrescar escena en vivo
              const chat = [...get().chat];
              const last = chat[chat.length - 1];
              chat[chat.length - 1] = {
                ...last,
                actions: [...(last.actions ?? []), ...(event.actions as ChatAction[])],
                actionsStatus: "accepted",
              };
              set({ chat });
              void get().refresh();
            } else {
              patchLast({ actions: event.actions as ChatAction[], actionsStatus: "pending" });
            }
          } else if (event.type === "error") {
            patchLast({ error: event.message });
          }
        }
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      patchLast({ error: message });
      reportError("chat", message);
    } finally {
      set({ chatBusy: false });
    }
  },

  resolveActions: async (msgIndex, accept) => {
    const chat = [...get().chat];
    const msg = chat[msgIndex];
    if (!msg?.actions || msg.actionsStatus !== "pending") return;

    if (!accept) {
      chat[msgIndex] = { ...msg, actionsStatus: "rejected" };
      set({ chat });
      return;
    }
    const scene = await guard(set, () => api.runBatch(msg.actions!), "acceptActions");
    chat[msgIndex] = { ...msg, actionsStatus: scene ? "accepted" : "error" };
    set(scene ? { chat, scene } : { chat });
    if (scene) void get().refreshKinematics();
  },
}));
