import { useStore } from "../state/store";

/* Overlay de ayuda de atajos (se abre con ? / F1 o el botón ⌨ de la barra de estado). */

const GROUPS: { title: string; rows: [string, string][] }[] = [
  {
    title: "Navegación",
    rows: [
      ["arrastrar", "Orbitar · clic derecho: desplazar · rueda: zoom al cursor"],
      ["F", "Encuadrar selección (o todo)"],
      ["doble-clic", "Enfocar un sólido"],
      ["Inicio / 0", "Vista ISO"],
      ["1 · 2 · 3", "Frente · Planta · Lateral"],
    ],
  },
  {
    title: "Selección",
    rows: [
      ["clic", "Seleccionar"],
      ["Ctrl+clic", "Añadir / quitar"],
      ["Shift+arrastrar", "Recuadro"],
      ["Ctrl+A", "Seleccionar todo"],
      ["Esc", "Deseleccionar / cancelar"],
    ],
  },
  {
    title: "Edición",
    rows: [
      ["Supr", "Eliminar selección"],
      ["Ctrl+Z · Ctrl+Y", "Deshacer · Rehacer"],
      ["Ctrl+D", "Duplicar"],
      ["M · R", "Gizmo mover · rotar"],
      ["← ↑ → ↓ · RePág/AvPág", "Empujar (Shift = fino 1 mm)"],
      ["Ctrl+S", "Guardar revisión"],
    ],
  },
  {
    title: "Vista",
    rows: [
      ["W", "Alambre / Sólido"],
      ["L", "Medir"],
      ["S", "Sección (cicla ejes)"],
      ["H · Alt+H", "Ocultar selección · Mostrar todo"],
      ["I", "Aislar selección"],
      ["? · F1", "Esta ayuda"],
    ],
  },
];

export default function ShortcutsHelp() {
  const open = useStore((s) => s.showShortcuts);
  const toggle = useStore((s) => s.toggleShortcuts);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={() => toggle(false)}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <h3>Atajos de teclado</h3>
        <div className="shortcuts-grid">
          {GROUPS.map((g) => (
            <div key={g.title} className="shortcuts-col">
              <h4>{g.title}</h4>
              <table>
                <tbody>
                  {g.rows.map(([k, d]) => (
                    <tr key={k}>
                      <td><kbd>{k}</kbd></td>
                      <td>{d}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
