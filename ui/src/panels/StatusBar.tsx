import { Keyboard, LayoutDashboard, AlertTriangle } from "lucide-react";
import { useStore } from "../state/store";
import { PANEL_ICONS } from "../ui/icons";
import Spinner from "../ui/Spinner";
import { togglePanel, resetLayout } from "../dock/dockApi";

/* Barra de estado inferior: toggles de los paneles-herramienta + unidades y conteo de
   sólidos. Cada toggle acopla/cierra su panel en el sistema de ventanas (Dockview). */

const PANELS = [
  { key: "history", label: "Historial" },
  { key: "reqs", label: "Requisitos" },
  { key: "bom", label: "BOM" },
  { key: "checks", label: "Validar" },
  { key: "kin", label: "Cinemática" },
  { key: "mates", label: "Ensamblaje" },
  { key: "fisica", label: "Física" },
  { key: "ensamblaje", label: "Montaje" },
  { key: "boceto", label: "Boceto" },
] as const;

export default function StatusBar() {
  const dockPanels = useStore((s) => s.dockPanels);
  const solids = useStore((s) => s.scene?.features.filter((f) => f.visible).length ?? 0);
  const cmds = useStore((s) => s.scene?.document.commands.length ?? 0);
  const toggleShortcuts = useStore((s) => s.toggleShortcuts);
  const busy = useStore((s) => s.busy);
  const busyLabel = useStore((s) => s.busyLabel);
  // robustez (V6.1): el backend avisa si el autoguardado no llega al disco o si abrió
  // un proyecto suprimiendo comandos rotos (schema drift)
  const autosaveFailed = useStore((s) => s.scene?.document.autosave_failed ?? null);
  const suppressed = useStore((s) => s.scene?.document.suppressed_commands?.length ?? 0);

  return (
    <footer className="statusbar">
      {PANELS.map((p) => {
        const Icon = PANEL_ICONS[p.key];
        const active = dockPanels.includes(p.key);
        return (
          <button
            key={p.key}
            className={`statusbtn ${active ? "active" : ""}`}
            title={p.label}
            onClick={() => togglePanel(p.key)}
          >
            <Icon size={14} strokeWidth={1.7} />
            <span>{p.label}{p.key === "history" ? ` (${cmds})` : ""}</span>
          </button>
        );
      })}
      <span className="status-right">
        {autosaveFailed && (
          <span
            className="busy-badge"
            role="status"
            style={{ color: "#d8703a" }}
            title={`El autoguardado falló: ${autosaveFailed}. Tus cambios están en memoria pero NO en disco.`}
          >
            <AlertTriangle size={13} strokeWidth={1.9} /> Sin guardar
          </span>
        )}
        {suppressed > 0 && (
          <span
            className="busy-badge"
            style={{ color: "#d8703a" }}
            title={`Se abrió el proyecto suprimiendo ${suppressed} comando(s) inválido(s). Revísalos en el Historial.`}
          >
            <AlertTriangle size={13} strokeWidth={1.9} /> {suppressed} suprimido{suppressed > 1 ? "s" : ""}
          </span>
        )}
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
