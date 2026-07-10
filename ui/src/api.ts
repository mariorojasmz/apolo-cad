import type {
  BomRow, CatalogItem, ChecksOut, CommandSchema, ConnectivityOut, CostingOut, DofOut, DropRequest, DropResult,
  GravityResult, KinematicsOut, MateRow, MotionKeyframe, MotionOut, ProjectInfo, RailConstraint,
  Requirements, RevisionInfo, SceneOut, SoundnessOut, StabilityOut, StabilityRequest,
} from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* sin cuerpo JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  schemas: () => fetch("/api/schemas").then((r) => json<CommandSchema[]>(r)),
  scene: () => fetch("/api/scene").then((r) => json<SceneOut>(r)),
  // Escena en forma DELTA (V6.2b): manda lo que el cliente ya tiene (rev por feature +
  // claves de definición + el epoch del proceso, V6.2e) → el server responde solo la
  // geometría que cambió, o el payload completo si el epoch no coincide (restart del API).
  sceneDelta: (revs: Record<string, number>, defs: string[], epoch: string | undefined) =>
    fetch("/api/scene/delta", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ revs, defs, epoch }),
    }).then((r) => json<SceneOut>(r)),
  catalog: () => fetch("/api/catalog").then((r) => json<CatalogItem[]>(r)),
  bom: () => fetch("/api/bom").then((r) => json<BomRow[]>(r)),
  costing: () => fetch("/api/costing.json").then((r) => json<CostingOut>(r)),
  requirements: () =>
    fetch("/api/requirements").then((r) => json<{ requirements: Requirements }>(r)),
  putRequirements: (fields: Requirements) =>
    fetch("/api/requirements", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields }),
    }).then((r) => json<{ ok: boolean; requirements: Requirements }>(r)),
  kinematics: () => fetch("/api/kinematics").then((r) => json<KinematicsOut>(r)),

  projects: () => fetch("/api/projects").then((r) => json<ProjectInfo[]>(r)),
  createProject: (name: string, template: string | null) =>
    fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, template }),
    }).then((r) => json<SceneOut>(r)),
  openProjectById: (id: number) =>
    fetch(`/api/projects/${id}/open`, { method: "POST" }).then((r) => json<SceneOut>(r)),
  deleteProject: (id: number) =>
    fetch(`/api/projects/${id}`, { method: "DELETE" }).then((r) => json<{ ok: boolean }>(r)),
  duplicateProject: (id: number) =>
    fetch(`/api/projects/${id}/duplicate`, { method: "POST" }).then((r) => json<{ id: number }>(r)),
  renameProject: (name: string) =>
    fetch("/api/projects/current", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then((r) => json<SceneOut>(r)),

  revisions: () => fetch("/api/revisions").then((r) => json<RevisionInfo[]>(r)),
  saveRevision: (note: string) =>
    fetch("/api/revisions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    }).then((r) => json<{ id: number }>(r)),
  restoreRevision: (id: number) =>
    fetch(`/api/revisions/${id}/restore`, { method: "POST" }).then((r) => json<SceneOut>(r)),

  saveConfiguration: (name: string) =>
    fetch("/api/configurations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then((r) => json<SceneOut>(r)),
  applyConfiguration: (name: string) =>
    fetch(`/api/configurations/${encodeURIComponent(name)}/apply`, { method: "POST" }).then((r) =>
      json<SceneOut>(r),
    ),
  // V6.4c: edición explícita de una variante {variable: expresión} (tabla de diseño), sin aplicar
  setConfiguration: (name: string, values: Record<string, string>) =>
    fetch(`/api/configurations/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    }).then((r) => json<SceneOut>(r)),
  deleteConfiguration: (name: string) =>
    fetch(`/api/configurations/${encodeURIComponent(name)}`, { method: "DELETE" }).then((r) =>
      json<SceneOut>(r),
    ),

  setColor: (id: string, color: string | null) =>
    fetch(`/api/features/${id}/color`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ color }),
    }).then((r) => json<SceneOut>(r)),
  deleteJoint: (name: string) =>
    fetch(`/api/joints/${encodeURIComponent(name)}`, { method: "DELETE" }).then((r) => json<SceneOut>(r)),
  motion: () => fetch("/api/motion").then((r) => json<MotionOut>(r)),
  saveMotion: (name: string, keyframes: MotionKeyframe[]) =>
    fetch("/api/motion", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, keyframes }),
    }).then((r) => json<MotionOut>(r)),
  deleteMotionStudy: (name: string) =>
    fetch("/api/motion", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then((r) => json<MotionOut>(r)),
  scanMotion: (name: string, steps: number) =>
    fetch("/api/motion/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, steps }),
    }).then((r) => json<{ colisiones: { t: number; interferencias: unknown[] }[] }>(r)),
  constraints: () => fetch("/api/constraints").then((r) => json<RailConstraint[]>(r)),
  solveConstraints: (values: Record<string, number>) =>
    fetch("/api/constraints/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    }).then((r) => json<{ values: Record<string, number> }>(r)),
  mates: () => fetch("/api/mates").then((r) => json<MateRow[]>(r)),
  deleteMate: (name: string) =>
    fetch(`/api/mates/${encodeURIComponent(name)}`, { method: "DELETE" }).then((r) => json<SceneOut>(r)),

  checks: (body: {
    carga_kg?: number;
    largo_paquete_mm?: number;
    ancho_paquete_mm?: number;
    velocidad_m_s?: number;
    joint_values?: Record<string, number>;
  }) =>
    fetch("/api/checks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<ChecksOut>(r)),

  dropTest: (body: DropRequest) =>
    fetch("/api/physics/drop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<DropResult>(r)),
  dropGif: async (body: DropRequest): Promise<Blob> => {
    const r = await fetch("/api/physics/drop.gif", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      let detail = r.statusText;
      try {
        detail = (await r.json()).detail ?? detail;
      } catch {
        /* sin cuerpo JSON */
      }
      throw new Error(detail);
    }
    return r.blob();
  },

  soundness: (withAutodetect: boolean) =>
    fetch("/api/assembly/soundness", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ with_autodetect: withAutodetect }),
    }).then((r) => json<SoundnessOut>(r)),

  dof: () => fetch("/api/assembly/dof").then((r) => json<DofOut>(r)),

  stability: (body: StabilityRequest) =>
    fetch("/api/assembly/stability", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<StabilityOut>(r)),

  connectivity: () => fetch("/api/connectivity").then((r) => json<ConnectivityOut>(r)),
  declareStructure: () =>
    fetch("/api/assembly/declare", { method: "POST" }).then((r) => json<SceneOut>(r)),
  deleteFastener: (name: string) =>
    fetch(`/api/fasteners/${encodeURIComponent(name)}`, { method: "DELETE" }).then((r) => json<SceneOut>(r)),
  deleteGround: (name: string) =>
    fetch(`/api/grounds/${encodeURIComponent(name)}`, { method: "DELETE" }).then((r) => json<SceneOut>(r)),

  // Igual que stability pero pide las poses por fotograma (para animar en el viewport).
  gravitySim: (body: StabilityRequest) =>
    fetch("/api/assembly/stability", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, include_frames: true }),
    }).then((r) => json<GravityResult>(r)),

  stabilityGif: async (body: StabilityRequest): Promise<Blob> => {
    const r = await fetch("/api/assembly/stability.gif", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      let detail = r.statusText;
      try {
        detail = (await r.json()).detail ?? detail;
      } catch {
        /* sin cuerpo JSON */
      }
      throw new Error(detail);
    }
    return r.blob();
  },

  runCommand: (type: string, params: Record<string, unknown>) =>
    fetch("/api/commands", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, params }),
    }).then((r) => json<SceneOut>(r)),

  runBatch: (actions: { type: string; params: Record<string, unknown> }[]) =>
    fetch("/api/commands/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actions: actions.map((a) => ({ type: a.type, params: a.params })) }),
    }).then((r) => json<SceneOut>(r)),

  editCommand: (id: string, params: Record<string, unknown>, transient = false, merge = false) =>
    fetch(`/api/commands/${id}?transient=${transient}&merge=${merge}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params }),
    }).then((r) => json<SceneOut>(r)),

  setVariable: (name: string, expression: string) =>
    fetch("/api/variables", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, expression }),
    }).then((r) => json<SceneOut>(r)),

  deleteVariable: (name: string) =>
    fetch(`/api/variables/${encodeURIComponent(name)}`, { method: "DELETE" }).then((r) =>
      json<SceneOut>(r),
    ),

  undo: () => fetch("/api/undo", { method: "POST" }).then((r) => json<SceneOut>(r)),
  redo: () => fetch("/api/redo", { method: "POST" }).then((r) => json<SceneOut>(r)),

  setVisibility: (id: string, visible: boolean) =>
    fetch(`/api/features/${id}/visibility`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ visible }),
    }).then((r) => json<SceneOut>(r)),

  setSketchGuide: (id: string, guide: boolean) =>
    fetch(`/api/features/${id}/sketch-guide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ guide }),
    }).then((r) => json<SceneOut>(r)),

  bulkVisibility: (ids: string[], visible: boolean) =>
    fetch("/api/features/visibility", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, visible }),
    }).then((r) => json<SceneOut>(r)),

  newProject: (name: string) =>
    fetch("/api/project/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then((r) => json<SceneOut>(r)),

  openProject: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch("/api/project/open", { method: "POST", body: form }).then((r) =>
      json<SceneOut>(r),
    );
  },

  importStep: (file: File, split: boolean) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`/api/import?split=${split}`, { method: "POST", body: form }).then((r) =>
      json<SceneOut>(r),
    );
  },

  chat: (messages: { role: string; content: string }[], auto = false) =>
    fetch("/api/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, auto }),
    }),
};

export function connectWs(onChanged: () => void, onReconnect?: () => void): () => void {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let ws: WebSocket | null = null;
  let closed = false;
  let hadOpen = false; // ¿ya hubo una conexión antes? → distinguir la primera de una reconexión

  const open = () => {
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
      // reconexión (V6.2e Fix 2): pudimos perder `document_changed` mientras estuvo caído
      // (o el API reinició y los revs renacieron) → refresco COMPLETO, no delta.
      if (hadOpen) onReconnect?.();
      hadOpen = true;
    };
    ws.onmessage = (ev) => {
      try {
        if (JSON.parse(ev.data).type === "document_changed") onChanged();
      } catch {
        /* mensaje no JSON */
      }
    };
    ws.onclose = () => {
      if (!closed) setTimeout(open, 2000);
    };
  };
  open();
  return () => {
    closed = true;
    ws?.close();
  };
}
