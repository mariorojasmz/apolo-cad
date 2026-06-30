import type { DockviewApi, IDockviewPanel, Direction } from "dockview-core";
import { useStore } from "../state/store";

/* Singleton del API de Dockview + helpers de docking. Vive fuera de React para que la
   StatusBar y los atajos puedan ordenar al layout (abrir/cerrar/restablecer) sin prop-drilling.
   El viewport es el centro FIJO (grupo bloqueado → nunca se mueve ni se re-monta → no pierde
   el contexto WebGL). */

export const LAYOUT_KEY = "apolo.layout.v1";

export interface PanelMeta {
  id: string;
  title: string;
  component: string;
}

// paneles-herramienta conmutables desde la StatusBar (tree/properties/chat/viewport
// forman el layout por defecto y no se listan aquí).
export const TOOL_PANELS: PanelMeta[] = [
  { id: "history", title: "Historial", component: "history" },
  { id: "bom", title: "Lista de materiales", component: "bom" },
  { id: "checks", title: "Validaciones", component: "checks" },
  { id: "kin", title: "Cinemática", component: "kin" },
  { id: "mates", title: "Ensamblaje", component: "mates" },
  { id: "fisica", title: "Física", component: "fisica" },
  { id: "ensamblaje", title: "Montaje", component: "ensamblaje" },
];

let _api: DockviewApi | null = null;

export function setDockApi(api: DockviewApi | null): void {
  _api = api;
}

/** Bloquea el grupo del viewport para que no se pueda arrastrar/cerrar (centro fijo). */
export function lockViewport(api: DockviewApi): void {
  const vp = api.getPanel("viewport");
  if (vp) vp.group.locked = true;
}

/** Construye el layout por defecto: viewport (centro) · árbol (izq) · propiedades+chat (der). */
export function buildDefaultLayout(api: DockviewApi): void {
  api.clear();
  const vp = api.addPanel({
    id: "viewport",
    component: "viewport",
    tabComponent: "locked",
    title: "Vista 3D",
    renderer: "always", // nunca destruir el canvas WebGL aunque quede oculto
  });
  api.addPanel({
    id: "tree",
    component: "tree",
    title: "Árbol",
    position: { referencePanel: "viewport", direction: "left" },
  });
  const props = api.addPanel({
    id: "properties",
    component: "properties",
    title: "Propiedades",
    position: { referencePanel: "viewport", direction: "right" },
  });
  api.addPanel({
    id: "chat",
    component: "chat",
    title: "Asistente IA",
    position: { referencePanel: "properties", direction: "within" },
  });
  props.api.setActive();
  vp.group.locked = true;
}

/** Restablece la disposición por defecto SIN destruir el viewport (preserva el contexto
   WebGL): cierra el resto de paneles y vuelve a acoplar árbol/propiedades/chat alrededor. */
export function resetLayout(): void {
  const api = _api;
  if (!api) return;
  try {
    localStorage.removeItem(LAYOUT_KEY);
  } catch {
    /* storage no disponible */
  }
  if (!api.getPanel("viewport")) {
    // sin viewport (estado corrupto) → reconstrucción completa
    buildDefaultLayout(api);
    return;
  }
  // cerrar todo menos el viewport (snapshot: close() muta api.panels)
  api.panels.filter((p) => p.id !== "viewport").forEach((p) => p.api.close());
  api.addPanel({
    id: "tree",
    component: "tree",
    title: "Árbol",
    position: { referencePanel: "viewport", direction: "left" },
  });
  const props = api.addPanel({
    id: "properties",
    component: "properties",
    title: "Propiedades",
    position: { referencePanel: "viewport", direction: "right" },
  });
  api.addPanel({
    id: "chat",
    component: "chat",
    title: "Asistente IA",
    position: { referencePanel: "properties", direction: "within" },
  });
  props.api.setActive();
  lockViewport(api);
}

/** Abre el panel si no está; si ya está, lo cierra (toggle de la StatusBar). */
export function togglePanel(id: string): void {
  const api = _api;
  if (!api) return;
  const existing = api.getPanel(id);
  if (existing) {
    existing.api.close();
    return;
  }
  const meta = TOOL_PANELS.find((p) => p.id === id);
  if (!meta) return;
  // apila los paneles-herramienta en el mismo grupo (pestañas) bajo el viewport
  const sibling = TOOL_PANELS.map((p) => api.getPanel(p.id)).find(Boolean) as IDockviewPanel | undefined;
  const position = sibling
    ? { referencePanel: sibling, direction: "within" as Direction }
    : { referencePanel: "viewport", direction: "below" as Direction };
  const panel = api.addPanel({ id, component: meta.component, title: meta.title, position });
  panel.api.setActive();
}

/** Sincroniza al store la lista de paneles presentes (para el resaltado de la StatusBar). */
export function syncDockPanels(api: DockviewApi): void {
  useStore.getState().setDockPanels(api.panels.map((p) => p.id));
}
