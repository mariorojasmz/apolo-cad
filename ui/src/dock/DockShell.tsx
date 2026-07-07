import { DockviewReact } from "dockview-react";
import type { DockviewReadyEvent, IDockviewPanelHeaderProps } from "dockview-react";
import { themeAbyss } from "dockview-core";
import "dockview-core/dist/styles/dockview.css";
import type { ComponentType } from "react";

import Tree from "../panels/Tree";
import Properties from "../panels/Properties";
import ChatPanel from "../chat/ChatPanel";
import HistoryPanel from "../panels/HistoryPanel";
import RequirementsPanel from "../panels/RequirementsPanel";
import BomPanel from "../panels/BomPanel";
import ChecksPanel from "../panels/ChecksPanel";
import KinematicsPanel from "../panels/KinematicsPanel";
import MatesPanel from "../panels/MatesPanel";
import PhysicsPanel from "../panels/PhysicsPanel";
import AssemblyPanel from "../panels/AssemblyPanel";
import SketchBlockPanel from "../panels/SketchBlockPanel";
import Viewport from "../viewport/Viewport";
import { setDockApi, buildDefaultLayout, lockViewport, syncDockPanels, LAYOUT_KEY } from "./dockApi";

/* Shell de ventanas acoplables (Dockview). El viewport es el centro fijo; el resto de
   paneles se acoplan/redimensionan/agrupan en pestañas y el layout se guarda en localStorage. */

// cada panel lee sus datos del store; envolvemos para que llene su panel de Dockview.
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
  tree: pane(Tree),
  properties: pane(Properties),
  chat: pane(ChatPanel),
  history: pane(HistoryPanel),
  reqs: pane(RequirementsPanel),
  bom: pane(BomPanel),
  checks: pane(ChecksPanel),
  kin: pane(KinematicsPanel),
  mates: pane(MatesPanel),
  fisica: pane(PhysicsPanel),
  ensamblaje: pane(AssemblyPanel),
  boceto: pane(SketchBlockPanel),
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

  let timer: ReturnType<typeof setTimeout>;
  api.onDidLayoutChange(() => {
    syncDockPanels(api);
    clearTimeout(timer);
    timer = setTimeout(() => {
      try {
        localStorage.setItem(LAYOUT_KEY, JSON.stringify(api.toJSON()));
      } catch {
        /* storage no disponible */
      }
    }, 300);
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
