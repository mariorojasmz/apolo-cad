import { Keyboard } from "lucide-react";
import { useStore } from "../state/store";
import { PANEL_ICONS } from "../ui/icons";
import Spinner from "../ui/Spinner";

/* Barra de estado inferior: toggles de los 6 paneles (antes en el TopBar) + unidades
   y conteo de sólidos. Cada toggle abre/cierra su panel en el BottomDock. */

const PANELS = [
  { key: "history", label: "Historial" },
  { key: "bom", label: "BOM" },
  { key: "checks", label: "Validar" },
  { key: "kin", label: "Cinemática" },
  { key: "mates", label: "Ensamblaje" },
  { key: "fisica", label: "Física" },
  { key: "ensamblaje", label: "Montaje" },
] as const;

export default function StatusBar() {
  const bottomPanel = useStore((s) => s.bottomPanel);
  const setBottomPanel = useStore((s) => s.setBottomPanel);
  const solids = useStore((s) => s.scene?.features.filter((f) => f.visible).length ?? 0);
  const cmds = useStore((s) => s.scene?.document.commands.length ?? 0);
  const toggleShortcuts = useStore((s) => s.toggleShortcuts);
  const busy = useStore((s) => s.busy);
  const busyLabel = useStore((s) => s.busyLabel);

  return (
    <footer className="statusbar">
      {PANELS.map((p) => {
        const Icon = PANEL_ICONS[p.key];
        const active = bottomPanel === p.key;
        return (
          <button
            key={p.key}
            className={`statusbtn ${active ? "active" : ""}`}
            title={p.label}
            onClick={() => setBottomPanel(active ? "none" : p.key)}
          >
            <Icon size={14} strokeWidth={1.7} />
            <span>{p.label}{p.key === "history" ? ` (${cmds})` : ""}</span>
          </button>
        );
      })}
      <span className="status-right">
        {busy && (
          <span className="busy-badge" role="status" aria-live="polite">
            <Spinner size={13} />
            {busyLabel ?? "Trabajando…"}
          </span>
        )}
        <button className="statusbtn" title="Atajos de teclado (?)" onClick={() => toggleShortcuts()}>
          <Keyboard size={14} strokeWidth={1.7} />
        </button>
        <span>mm</span>
        <span>{solids} sólidos</span>
      </span>
    </footer>
  );
}
