import { useEffect } from "react";
import { useStore } from "./state/store";
import TopBar from "./panels/TopBar";
import Ribbon from "./panels/Ribbon";
import Tree from "./panels/Tree";
import RightDock from "./panels/RightDock";
import BottomDock from "./panels/BottomDock";
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
import Viewport from "./viewport/Viewport";

export default function App() {
  const init = useStore((s) => s.init);
  const error = useStore((s) => s.error);
  const setError = useStore((s) => s.setError);
  const busy = useStore((s) => s.busy);

  useEffect(() => {
    void init();
  }, [init]);

  return (
    <div className={`app${busy ? " busy" : ""}`} aria-busy={busy}>
      <TopProgress />
      <TopBar />
      <Ribbon />
      <main className="workspace">
        <Tree />
        <Viewport />
        <RightDock />
      </main>
      <BottomDock />
      <StatusBar />
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
