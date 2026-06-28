import type { CSSProperties } from "react";
import { X } from "lucide-react";
import { useStore } from "../state/store";
import { SplitHandle, useSplitter } from "../ui/Splitter";
import HistoryPanel from "./HistoryPanel";
import BomPanel from "./BomPanel";
import ChecksPanel from "./ChecksPanel";
import KinematicsPanel from "./KinematicsPanel";
import MatesPanel from "./MatesPanel";
import PhysicsPanel from "./PhysicsPanel";
import AssemblyPanel from "./AssemblyPanel";

/* Dock inferior redimensionable. Envuelve los 6 paneles SIN modificarlos: cada uno
   se auto-gestiona (`bottomPanel===x`), así que dentro de .dock-body solo pinta el
   activo; los demás devuelven null. Reemplaza los antiguos paneles en flujo de 160px. */

const TITLES: Record<string, string> = {
  history: "Historial",
  bom: "Lista de materiales",
  checks: "Validaciones",
  kin: "Cinemática",
  mates: "Ensamblaje",
  fisica: "Física",
  ensamblaje: "Validación de ensamblaje",
};

export default function BottomDock() {
  const panel = useStore((s) => s.bottomPanel);
  const setBottomPanel = useStore((s) => s.setBottomPanel);
  const { size, onPointerDown } = useSplitter({
    initial: 220, min: 120, max: 520, axis: "y", invert: true, storageKey: "apolo.dock.h",
  });

  if (panel === "none") return null;

  return (
    <section className="bottomdock" style={{ "--bottomdock-h": `${size}px` } as CSSProperties}>
      <SplitHandle axis="y" onPointerDown={onPointerDown} />
      <header className="dock-head">
        <span>{TITLES[panel] ?? panel}</span>
        <button title="Cerrar panel" onClick={() => setBottomPanel("none")}>
          <X size={15} />
        </button>
      </header>
      <div className="dock-body">
        <HistoryPanel />
        <BomPanel />
        <ChecksPanel />
        <KinematicsPanel />
        <MatesPanel />
        <PhysicsPanel />
        <AssemblyPanel />
      </div>
    </section>
  );
}
