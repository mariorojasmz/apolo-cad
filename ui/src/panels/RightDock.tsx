import type { CSSProperties } from "react";
import Properties from "./Properties";
import ChatPanel from "../chat/ChatPanel";
import { SplitHandle, useSplitter } from "../ui/Splitter";

/* Columna derecha: Propiedades (arriba) + divisor arrastrable + Asistente IA (abajo).
   El splitter ajusta --props-h; el chat tiene min-height en CSS, así que su input
   queda SIEMPRE visible (arregla el bug de overflow). */

export default function RightDock() {
  const { size, onPointerDown } = useSplitter({
    initial: 320, min: 140, max: 900, axis: "y", storageKey: "apolo.props.h",
  });

  return (
    <div className="right-dock" style={{ "--props-h": `${size}px` } as CSSProperties}>
      <Properties />
      <SplitHandle axis="y" onPointerDown={onPointerDown} />
      <ChatPanel />
    </div>
  );
}
