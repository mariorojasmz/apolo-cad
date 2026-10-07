import { useRef, useState } from "react";
import { ChevronDown, Download, FolderOpen, Home, Save, Upload } from "lucide-react";
import { useStore } from "../state/store";
import SelectorPantalla from "../visor/SelectorPantalla";
import HistorialCambios from "./HistorialCambios";

/* Cabecera slim: marca/proyecto · pestañas de entorno (Modelar/Planos/Simular) ·
   deshacer/rehacer con su lista de cambios · Visor | Completo · menú Archivo. Los toggles de
   paneles viven en la StatusBar (Completo). */

export default function TopBar() {
  const doc = useStore((s) => s.scene?.document);
  const showDrawing = useStore((s) => s.showDrawing);
  // Selectores por acción (no `useStore()` pelado): sin selector, la cabecera se re-renderizaba
  // con CADA cambio de la store (p. ej. cada token del chat en streaming).
  const openProject = useStore((s) => s.openProject);
  const openDrawing = useStore((s) => s.openDrawing);
  const importStep = useStore((s) => s.importStep);
  const openHome = useStore((s) => s.openHome);
  const renameProject = useStore((s) => s.renameProject);
  const fileRef = useRef<HTMLInputElement>(null);
  const stepRef = useRef<HTMLInputElement>(null);
  const [menu, setMenu] = useState(false);
  const close = () => setMenu(false);

  // Mismo proyecto → NO `adoptScene` (borraría selección/chat/juntas); la store aplica solo la escena.
  const rename = () => {
    const next = window.prompt("Nombre del proyecto:", doc?.name ?? "");
    if (next && next.trim()) void renameProject(next.trim());
  };

  return (
    <header className="topbar">
      <button className="icon-btn brand-btn" title="Proyectos y revisiones" onClick={() => openHome(true)}>
        <Home size={16} /> Apolo CAD
      </button>
      <span className="project-name" title="Doble clic para renombrar" onDoubleClick={rename}>
        {doc?.name ?? "…"}
      </span>

      <span className="env-tabs">
        <span className="tab active">Modelar</span>
        <button
          className={`tab tab-btn ${showDrawing ? "active" : ""}`}
          title="Generar planos del modelo (SVG / DXF / PDF)"
          onClick={() => openDrawing(true)}
        >
          Planos
        </button>
        <span className="tab disabled" title="Fase 6">Simular</span>
      </span>

      <span className="spacer" />

      <HistorialCambios sentido="deshacer" />
      <HistorialCambios sentido="rehacer" />
      <SelectorPantalla />

      <span className="menu">
        <button className="icon-btn" onClick={() => setMenu((m) => !m)} title="Archivo">
          Archivo <ChevronDown size={14} />
        </button>
        {menu && (
          <div className="menu-pop" onMouseLeave={close}>
            <button onClick={() => { close(); openHome(true); }}>
              <FolderOpen size={15} /> Proyectos…
            </button>
            <button onClick={() => { close(); fileRef.current?.click(); }}>
              <Upload size={15} /> Abrir .apolo…
            </button>
            <button onClick={() => { close(); window.open("/api/project/file", "_blank"); }}>
              <Save size={15} /> Guardar .apolo
            </button>
            <div className="sep" />
            <button onClick={() => { close(); stepRef.current?.click(); }}>
              <Upload size={15} /> Importar STEP…
            </button>
            <button onClick={() => { close(); window.open("/api/export/step", "_blank"); }}>
              <Download size={15} /> Exportar STEP
            </button>
            <button onClick={() => { close(); window.open("/api/export/stl", "_blank"); }}>
              <Download size={15} /> Exportar STL
            </button>
            <button onClick={() => { close(); window.dispatchEvent(new CustomEvent("apolo:export-gltf")); }}>
              <Download size={15} /> Exportar glTF
            </button>
          </div>
        )}
      </span>

      <input
        ref={fileRef}
        type="file"
        accept=".apolo"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void openProject(f);
          e.target.value = "";
        }}
      />
      <input
        ref={stepRef}
        type="file"
        accept=".step,.stp"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void importStep(f, window.confirm("¿Separar cada sólido del STEP en una pieza independiente?"));
          e.target.value = "";
        }}
      />
    </header>
  );
}
