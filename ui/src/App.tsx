import { useEffect } from "react";
import { useStore } from "./state/store";
import TopBar from "./panels/TopBar";
import Ribbon from "./panels/Ribbon";
import DockShell from "./dock/DockShell";
import StatusBar from "./panels/StatusBar";
import CommandDialog from "./panels/CommandDialog";
import VariablesDialog from "./panels/VariablesDialog";
import LibraryDialog from "./panels/LibraryDialog";
import DrawingDialog from "./panels/DrawingDialog";
import HomeScreen from "./panels/HomeScreen";
import SketcherDialog from "./panels/SketcherDialog";
import ContextMenu from "./panels/ContextMenu";
import ShortcutsHelp from "./panels/ShortcutsHelp";
import TopProgress from "./panels/TopProgress";
import BusyOverlay from "./panels/BusyOverlay";
import CapaVisor from "./visor/CapaVisor";
import { useVisor } from "./visor/estado";

export default function App() {
  const init = useStore((s) => s.init);
  const error = useStore((s) => s.error);
  const setError = useStore((s) => s.setError);
  const busy = useStore((s) => s.busy);
  // Visor: sin Ribbon ni StatusBar; el dock maximiza el 3D (dock/dockApi.ts::setModoVisor) y
  // la capa del visor flota encima. El DockShell se monta igual en los dos modos (no se re-monta).
  const visor = useVisor((s) => s.modo === "visor");
  // con el Árbol abierto, los controles del 3D se corren a su derecha (visor/cajones.css)
  const arbol = useVisor((s) => s.modo === "visor" && s.cajonIzq);

  useEffect(() => {
    void init();
  }, [init]);

  return (
    <div
      className={`app${busy ? " busy" : ""}${visor ? " modo-visor" : ""}${arbol ? " visor-arbol" : ""}`}
      aria-busy={busy}
    >
      <TopProgress />
      <TopBar />
      {!visor && <Ribbon />}
      <DockShell />
      {visor && <CapaVisor />}
      {!visor && <StatusBar />}
      <CommandDialog />
      <VariablesDialog />
      <LibraryDialog />
      <DrawingDialog />
      <HomeScreen />
      <SketcherDialog />
      <ContextMenu />
      <ShortcutsHelp />
      <BusyOverlay />
      {error && (
        <div className="toast" onClick={() => setError(null)}>
          ⚠ {error}
        </div>
      )}
    </div>
  );
}
