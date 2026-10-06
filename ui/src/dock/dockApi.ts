import type { DockviewApi, IDockviewPanel, Direction } from "dockview-core";
import { useStore } from "../state/store";
import { useVisor } from "../visor/estado";
import { HERRAMIENTAS, PANELES } from "./paneles";

/* Singleton del API de Dockview + helpers de docking. Vive fuera de React para que la
   StatusBar y los atajos puedan ordenar al layout (abrir/cerrar/restablecer) sin prop-drilling.
   El viewport es el centro FIJO (grupo bloqueado → nunca se mueve ni se re-monta → no pierde
   el contexto WebGL). El modo Visor maximiza ese grupo (`setModoVisor`), no lo re-monta. */

export const LAYOUT_KEY = "apolo.layout.v1";

export interface PanelMeta {
  id: string;
  title: string;
  component: string;
}

// paneles-herramienta conmutables desde la StatusBar (tree/properties/chat/viewport
// forman el layout por defecto y no se listan aquí). Id y título salen de `paneles.ts`.
export const TOOL_PANELS: PanelMeta[] = HERRAMIENTAS.map((id) => ({
  id,
  title: PANELES[id].titulo,
  component: id,
}));

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
    title: PANELES.tree.titulo,
    position: { referencePanel: "viewport", direction: "left" },
  });
  const props = api.addPanel({
    id: "properties",
    component: "properties",
    title: PANELES.properties.titulo,
    position: { referencePanel: "viewport", direction: "right" },
  });
  api.addPanel({
    id: "chat",
    component: "chat",
    title: PANELES.chat.titulo,
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
  // sólo la StatusBar lo llama y en el visor no está montada; si igual llega, se rehace el
  // layout de Completo y el visor se vuelve a aplicar encima
  if (api.hasMaximizedGroup()) api.exitMaximizedGroup();
  if (!api.getPanel("viewport")) {
    // sin viewport (estado corrupto) → reconstrucción completa
    buildDefaultLayout(api);
    aplicarModoActual();
    return;
  }
  // cerrar todo menos el viewport (snapshot: close() muta api.panels)
  api.panels.filter((p) => p.id !== "viewport").forEach((p) => p.api.close());
  api.addPanel({
    id: "tree",
    component: "tree",
    title: PANELES.tree.titulo,
    position: { referencePanel: "viewport", direction: "left" },
  });
  const props = api.addPanel({
    id: "properties",
    component: "properties",
    title: PANELES.properties.titulo,
    position: { referencePanel: "viewport", direction: "right" },
  });
  api.addPanel({
    id: "chat",
    component: "chat",
    title: PANELES.chat.titulo,
    position: { referencePanel: "properties", direction: "within" },
  });
  props.api.setActive();
  lockViewport(api);
  aplicarModoActual();
}

/** Abre el panel si no está; si ya está, lo cierra (toggle de la StatusBar). En el visor no
   hace nada: acoplar un panel saca a Dockview del maximizado (los paneles del visor van en
   cajones, plan modo-visor F3). */
export function togglePanel(id: string): void {
  const api = _api;
  if (!api || useVisor.getState().modo === "visor") return;
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

/** Guarda el layout de Completo. Nunca con un grupo maximizado: Dockview serializa el
   maximizado (`maximizedNode`) y el próximo arranque abriría Completo maximizado. */
export function guardarLayout(api: DockviewApi): void {
  if (api.hasMaximizedGroup()) return;
  try {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(api.toJSON()));
  } catch {
    /* storage no disponible */
  }
}

/** Visor: maximiza el grupo del viewport y oculta su pestaña; el canvas es el mismo, no se
   re-monta (bitácora F0 del plan modo-visor). Completo: muestra la pestaña, sale del
   maximizado y guarda el layout A MANO: `exitMaximizedGroup()` no dispara
   `onDidLayoutChange`, así que sin esto lo guardado seguiría maximizado. */
export function setModoVisor(visor: boolean): void {
  const api = _api;
  const vp = api?.getPanel("viewport");
  if (!api || !vp) return;
  if (visor) {
    if (vp.group.activePanel !== vp) vp.api.setActive(); // con la pestaña oculta no se podría elegir
    if (!vp.api.isMaximized()) {
      if (api.hasMaximizedGroup()) api.exitMaximizedGroup(); // otro grupo maximizado en Completo
      api.maximizeGroup(vp);
    }
    vp.group.header.hidden = true;
  } else {
    vp.group.header.hidden = false;
    if (api.hasMaximizedGroup()) api.exitMaximizedGroup();
    guardarLayout(api);
  }
}

function aplicarModoActual(): void {
  setModoVisor(useVisor.getState().modo === "visor");
}

let _desvincular: (() => void) | null = null;

/** Al cargar: normaliza el maximizado que traiga el JSON (un layout guardado antes de esta
   regla), aplica el modo recordado y lo sigue. Si Dockview sale solo del maximizado con el
   visor puesto (p. ej. al activar otro grupo), lo vuelve a maximizar. */
export function vincularModo(api: DockviewApi): void {
  _desvincular?.();
  if (api.hasMaximizedGroup()) {
    api.exitMaximizedGroup();
    guardarLayout(api);
  }
  aplicarModoActual();
  const sinModo = useVisor.subscribe((s, prev) => {
    if (s.modo !== prev.modo) setModoVisor(s.modo === "visor");
  });
  const sinMax = api.onDidMaximizedGroupChange((e) => {
    if (!e.isMaximized && useVisor.getState().modo === "visor") setTimeout(aplicarModoActual, 0);
  });
  _desvincular = () => {
    sinModo();
    sinMax.dispose();
  };
}
