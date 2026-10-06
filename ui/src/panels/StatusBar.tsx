import { Keyboard, LayoutDashboard } from "lucide-react";
import { useStore } from "../state/store";
import { PANEL_ICONS } from "../ui/icons";
import Spinner from "../ui/Spinner";
import { togglePanel, resetLayout } from "../dock/dockApi";
import { HERRAMIENTAS, PANELES } from "../dock/paneles";
import AvisosDocumento from "./AvisosDocumento";

/* Barra de estado inferior: toggles de los paneles-herramienta + unidades y conteo de
   sólidos. Cada toggle acopla/cierra su panel en el sistema de ventanas (Dockview). Los
   rótulos salen de `dock/paneles.ts` (los mismos que la barra de paneles del visor). */

export default function StatusBar() {
  const dockPanels = useStore((s) => s.dockPanels);
  const solids = useStore((s) => s.scene?.features.filter((f) => f.visible).length ?? 0);
  const cmds = useStore((s) => s.scene?.document.commands.length ?? 0);
  const toggleShortcuts = useStore((s) => s.toggleShortcuts);
  const busy = useStore((s) => s.busy);
  const busyLabel = useStore((s) => s.busyLabel);

  return (
    <footer className="statusbar">
      {HERRAMIENTAS.map((key) => {
        const Icon = PANEL_ICONS[key];
        const label = PANELES[key].rotulo;
        const active = dockPanels.includes(key);
        return (
          <button
            key={key}
            className={`statusbtn ${active ? "active" : ""}`}
            title={label}
            onClick={() => togglePanel(key)}
          >
            <Icon size={14} strokeWidth={1.7} />
            <span>{label}{key === "history" ? ` (${cmds})` : ""}</span>
          </button>
        );
      })}
      <span className="status-right">
        <AvisosDocumento />
        {busy && (
          <span className="busy-badge" role="status" aria-live="polite">
            <Spinner size={13} />
            {busyLabel ?? "Trabajando…"}
          </span>
        )}
        <button className="statusbtn" title="Restablecer disposición de ventanas" onClick={() => resetLayout()}>
          <LayoutDashboard size={14} strokeWidth={1.7} />
        </button>
        <button className="statusbtn" title="Atajos de teclado (?)" onClick={() => toggleShortcuts()}>
          <Keyboard size={14} strokeWidth={1.7} />
        </button>
        <span>mm</span>
        <span>{solids} sólidos</span>
      </span>
    </footer>
  );
}
