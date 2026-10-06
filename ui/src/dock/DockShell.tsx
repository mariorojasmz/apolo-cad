import { DockviewReact } from "dockview-react";
import type { DockviewReadyEvent, IDockviewPanelHeaderProps } from "dockview-react";
import { themeAbyss } from "dockview-core";
import "dockview-core/dist/styles/dockview.css";
import type { ComponentType } from "react";

import Viewport from "../viewport/Viewport";
import {
  setDockApi, buildDefaultLayout, guardarLayout, lockViewport, syncDockPanels, vincularModo, LAYOUT_KEY,
} from "./dockApi";
import { PANELES } from "./paneles";

/* Shell de ventanas acoplables (Dockview). El viewport es el centro fijo; el resto de
   paneles se acoplan/redimensionan/agrupan en pestañas y el layout se guarda en localStorage.
   Los paneles salen de `paneles.ts`, que comparte con los cajones del visor. */

// cada panel lee sus datos del store; envolvemos para que llene su panel de Dockview.
// Se arma una vez, al cargar el módulo: Dockview necesita la misma función en cada render.
const pane = (C: ComponentType) =>
  function DockPane() {
    return (
      <div className="dock-pane">
        <C />
      </div>
    );
  };

const COMPONENTS = {
  viewport: function ViewportPane() {
    return (
      <div className="dock-pane dock-viewport">
        <Viewport />
      </div>
    );
  },
  ...Object.fromEntries(Object.entries(PANELES).map(([id, p]) => [id, pane(p.Componente)])),
};

// pestaña sin botón de cerrar para el viewport (centro fijo)
const TAB_COMPONENTS = {
  locked: function LockedTab(props: IDockviewPanelHeaderProps) {
    return <span className="dv-tab-locked">{props.api.title}</span>;
  },
};

function onReady(event: DockviewReadyEvent): void {
  const api = event.api;
  setDockApi(api);

  let restored = false;
  let saved: string | null = null;
  try {
    saved = localStorage.getItem(LAYOUT_KEY);
  } catch {
    saved = null;
  }
  if (saved) {
    try {
      api.fromJSON(JSON.parse(saved));
      restored = api.getPanel("viewport") != null;
    } catch {
      restored = false;
    }
  }
  if (!restored) buildDefaultLayout(api);
  lockViewport(api);
  syncDockPanels(api);
  vincularModo(api); // sale del maximizado guardado y aplica Visor | Completo

  let timer: ReturnType<typeof setTimeout>;
  api.onDidLayoutChange(() => {
    syncDockPanels(api);
    clearTimeout(timer);
    // con el visor (grupo maximizado) no persiste: lo hace setModoVisor al volver a Completo
    timer = setTimeout(() => guardarLayout(api), 300);
  });
}

export default function DockShell() {
  return (
    <div className="apolo-dock">
      <DockviewReact
        components={COMPONENTS}
        tabComponents={TAB_COMPONENTS}
        theme={themeAbyss}
        onReady={onReady}
      />
    </div>
  );
}
