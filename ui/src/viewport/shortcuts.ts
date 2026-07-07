import { api } from "../api";
import { useStore } from "../state/store";

/* Capa de atajos de teclado ("CAD pro"). Un único listener en window que delega:
   - acciones de documento/selección → store (getState)
   - acciones de vista/gizmo/sección/medida → handlers locales del Viewport
   Se instala una vez; lee los handlers por getter para no capturar closures viejos. */

type GizmoMode = "off" | "translate" | "rotate" | "scale";

export interface ShortcutHandlers {
  fitTo: () => void;
  setView: (name: "ISO" | "Frente" | "Lateral" | "Planta") => void;
  toggleShading: () => void;
  gizmoMode: () => GizmoMode;
  setGizmo: (mode: GizmoMode) => void;
  cycleSection: () => void;
  toggleMeasure: () => void;
  nudge: (dx: number, dy: number, dz: number) => void;
  isBusy: () => boolean; // gizmo/box-select/arrastre-directo en curso
}

function closeTopModal(s: ReturnType<typeof useStore.getState>): void {
  if (s.dialogSchema) s.openDialog(null);
  else if (s.sketcherOpen) s.closeSketcher();
  else if (s.showVariables) s.openVariables(false);
  else if (s.showLibrary) s.openLibrary(false);
  else if (s.showDrawing) s.openDrawing(false);
  else if (s.showHome) s.openHome(false);
}

export function installShortcuts(getHandlers: () => ShortcutHandlers | null): () => void {
  const onKey = (e: KeyboardEvent) => {
    const h = getHandlers();
    if (!h) return;
    const t = e.target as HTMLElement | null;
    if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;

    const s = useStore.getState();
    const modalOpen =
      !!s.dialogSchema || s.showVariables || s.showLibrary || s.showDrawing || s.showHome || s.sketcherOpen;

    // Escape: cascada (siempre permitido)
    if (e.key === "Escape") {
      if (s.pickRequest) return s.requestPick(null);
      if (s.contextMenu) return s.openContextMenu(null);
      if (s.showShortcuts) return s.toggleShortcuts(false);
      if (modalOpen) return closeTopModal(s);
      if (h.gizmoMode() !== "off") return h.setGizmo("off");
      if (s.selection.length) return s.clearSelection();
      return;
    }

    if (modalOpen || h.isBusy()) return;

    if (e.ctrlKey || e.metaKey) {
      const k = e.key.toLowerCase();
      if (k === "z") { e.preventDefault(); void (e.shiftKey ? s.redo() : s.undo()); }
      else if (k === "y") { e.preventDefault(); void s.redo(); }
      else if (k === "a") { e.preventDefault(); s.selectAll(); }
      else if (k === "d") { e.preventDefault(); void s.duplicateSelection(); }
      else if (k === "s") { e.preventDefault(); void api.saveRevision("Guardado manual").catch(() => {}); }
      return;
    }

    const step = e.shiftKey ? 1 : 10;
    switch (e.key) {
      case "Delete":
      case "Backspace": e.preventDefault(); void s.deleteSelection(); break;
      case "f": case "F": h.fitTo(); break;
      case "Home": case "0": h.setView("ISO"); break;
      case "1": h.setView("Frente"); break;
      case "2": h.setView("Planta"); break;
      case "3": h.setView("Lateral"); break;
      case "w": case "W": h.toggleShading(); break;
      case "m": case "M": case "g": case "G":
        h.setGizmo(h.gizmoMode() === "translate" ? "off" : "translate"); break;
      case "r": case "R":
        h.setGizmo(h.gizmoMode() === "rotate" ? "off" : "rotate"); break;
      case "h": case "H": e.preventDefault(); void (e.altKey ? s.showAll() : s.hideSelection()); break;
      case "i": case "I": void s.isolate(); break;
      case "l": case "L": h.toggleMeasure(); break;
      case "s": case "S": h.cycleSection(); break;
      case "?": e.preventDefault(); s.toggleShortcuts(); break;
      case "F1": e.preventDefault(); s.toggleShortcuts(); break;
      case "ArrowLeft": e.preventDefault(); h.nudge(-step, 0, 0); break;
      case "ArrowRight": e.preventDefault(); h.nudge(step, 0, 0); break;
      case "ArrowUp": e.preventDefault(); h.nudge(0, step, 0); break;
      case "ArrowDown": e.preventDefault(); h.nudge(0, -step, 0); break;
      case "PageUp": e.preventDefault(); h.nudge(0, 0, step); break;
      case "PageDown": e.preventDefault(); h.nudge(0, 0, -step); break;
    }
  };
  window.addEventListener("keydown", onKey);
  return () => window.removeEventListener("keydown", onKey);
}
