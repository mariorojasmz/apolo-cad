import { useMemo, useState } from "react";
import { Trash2 } from "lucide-react";
import { selectFeatures, useStore } from "../state/store";
import type { FeatureOut } from "../types";

/* Árbol del modelo con sub-ensamblajes: las piezas generadas por un mismo
   comando (transportador, brazo, patrón…) se agrupan en un nodo colapsable. */

export default function Tree() {
  const features = useStore(selectFeatures);
  const selection = useStore((s) => s.selection);
  const select = useStore((s) => s.select);
  const toggleSelect = useStore((s) => s.toggleSelect);
  const toggleVisibility = useStore((s) => s.toggleVisibility);
  const runCommand = useStore((s) => s.runCommand);
  const openContextMenu = useStore((s) => s.openContextMenu);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const onRowContext = (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    if (!selection.includes(id)) select([id]);
    openContextMenu({ x: e.clientX, y: e.clientY, targetId: id });
  };
  const focusFeature = (id: string) => {
    select([id]);
    window.dispatchEvent(new CustomEvent("apolo:fit", { detail: { id } }));
  };

  const groups = useMemo(() => {
    const byCmd = new Map<string, FeatureOut[]>();
    for (const f of features) {
      const list = byCmd.get(f.command_id) ?? [];
      list.push(f);
      byCmd.set(f.command_id, list);
    }
    return [...byCmd.entries()];
  }, [features]);

  const onItemClick = (e: React.MouseEvent, id: string) => {
    if (e.ctrlKey || e.metaKey) toggleSelect(id);
    else select(selection.length === 1 && selection[0] === id ? [] : [id]);
  };

  const row = (f: FeatureOut, indent = false) => (
    <li
      key={f.id}
      className={`${selection.includes(f.id) ? "selected" : ""} ${indent ? "indent" : ""}`}
      title="Clic: seleccionar · Ctrl+clic: añadir/quitar · doble-clic: enfocar · clic derecho: menú"
      onClick={(e) => onItemClick(e, f.id)}
      onDoubleClick={() => focusFeature(f.id)}
      onContextMenu={(e) => onRowContext(e, f.id)}
    >
      <button
        className="eye"
        title={f.visible ? "Ocultar" : "Mostrar"}
        onClick={(e) => {
          e.stopPropagation();
          void toggleVisibility(f.id);
        }}
      >
        {f.visible ? "👁" : "—"}
      </button>
      <span className="swatch" style={{ background: f.color }} />
      <span className={f.visible ? "" : "muted"}>{f.name}</span>
      <span className="fid">{f.id}</span>
      <button
        className="row-del"
        title="Eliminar este sólido"
        onClick={(e) => {
          e.stopPropagation();
          void runCommand("delete_feature", { feature: f.id });
        }}
      >
        <Trash2 size={12} />
      </button>
    </li>
  );

  return (
    <aside className="tree">
      <h3>Árbol del modelo</h3>
      {features.length === 0 && (
        <p className="hint">Escena vacía. Crea geometría con la toolbar o pídesela al asistente IA.</p>
      )}
      <ul>
        {groups.map(([cmdId, members]) => {
          if (members.length === 1) return row(members[0]);
          const label = members[0].name.includes(" · ")
            ? members[0].name.split(" · ")[0]
            : members[0].name.replace(/ \(\d+\)$/, "");
          const isCollapsed = collapsed.has(cmdId);
          const allIds = members.map((m) => m.id);
          const groupSelected = allIds.every((id) => selection.includes(id));
          return (
            <li key={cmdId} className="tree-group">
              <div
                className={`group-head ${groupSelected ? "selected" : ""}`}
                title="Clic: seleccionar grupo entero"
                onClick={() => select(groupSelected ? [] : allIds)}
              >
                <button
                  className="eye"
                  title={isCollapsed ? "Desplegar" : "Plegar"}
                  onClick={(e) => {
                    e.stopPropagation();
                    const next = new Set(collapsed);
                    if (isCollapsed) next.delete(cmdId);
                    else next.add(cmdId);
                    setCollapsed(next);
                  }}
                >
                  {isCollapsed ? "▸" : "▾"}
                </button>
                <strong>{label}</strong>
                <span className="fid">{members.length} piezas · {cmdId}</span>
              </div>
              {!isCollapsed && <ul>{members.map((m) => row(m, true))}</ul>}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
