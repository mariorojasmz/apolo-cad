import type { LucideIcon } from "lucide-react";
import { Copy, Crop, Eye, EyeOff, Focus, MousePointerSquareDashed, Trash2 } from "lucide-react";
import { useStore } from "../state/store";

/* Menú contextual (clic derecho en viewport o árbol). Lee store.contextMenu y
   actúa sobre la selección. "Centrar/Encuadrar" pide el encuadre al viewport vía
   CustomEvent("apolo:fit") para no acoplar el store al three.js. */

const fitEvent = (id?: string) =>
  window.dispatchEvent(new CustomEvent("apolo:fit", { detail: { id } }));

export default function ContextMenu() {
  const cm = useStore((s) => s.contextMenu);
  const close = useStore((s) => s.openContextMenu);
  if (!cm) return null;
  const s = useStore.getState();
  const run = (fn: () => void) => {
    fn();
    close(null);
  };

  const Item = ({ icon: Icon, label, onClick, danger }: {
    icon: LucideIcon; label: string; onClick: () => void; danger?: boolean;
  }) => (
    <button className={`ctx-item${danger ? " danger" : ""}`} onClick={() => run(onClick)}>
      <Icon size={14} /> {label}
    </button>
  );

  const left = Math.min(cm.x, window.innerWidth - 196);
  const top = Math.min(cm.y, window.innerHeight - 250);

  return (
    <>
      <div
        className="ctx-backdrop"
        onClick={() => close(null)}
        onContextMenu={(e) => { e.preventDefault(); close(null); }}
      />
      <div className="ctx-menu" style={{ left, top }}>
        {cm.targetId ? (
          <>
            <Item icon={Trash2} label="Eliminar" danger onClick={() => void s.deleteSelection()} />
            <Item icon={Copy} label="Duplicar" onClick={() => void s.duplicateSelection()} />
            <Item icon={EyeOff} label="Ocultar" onClick={() => void s.hideSelection()} />
            <Item icon={Focus} label="Aislar" onClick={() => void s.isolate()} />
            <Item icon={Crop} label="Centrar" onClick={() => fitEvent(cm.targetId ?? undefined)} />
            <div className="ctx-sep" />
            <Item icon={Eye} label="Mostrar todo" onClick={() => void s.showAll()} />
          </>
        ) : (
          <>
            <Item icon={Crop} label="Encuadrar todo" onClick={() => fitEvent()} />
            <Item icon={Eye} label="Mostrar todo" onClick={() => void s.showAll()} />
            <Item icon={MousePointerSquareDashed} label="Deseleccionar" onClick={() => s.clearSelection()} />
          </>
        )}
      </div>
    </>
  );
}
