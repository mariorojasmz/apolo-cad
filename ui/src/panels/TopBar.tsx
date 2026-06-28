import { useRef, useState } from "react";
import { ChevronDown, Download, FolderOpen, Home, Redo2, Save, Undo2, Upload } from "lucide-react";
import { useStore } from "../state/store";

/* Cabecera slim: marca/proyecto · pestañas de entorno (Modelar/Planos/Simular) ·
   deshacer/rehacer · menú Archivo. Los 6 toggles de paneles se movieron a la StatusBar. */

export default function TopBar() {
  const doc = useStore((s) => s.scene?.document);
  const busy = useStore((s) => s.busy);
  const { undo, redo, openProject, showDrawing, openDrawing, importStep, openHome, adoptScene, setError } =
    useStore();
  const fileRef = useRef<HTMLInputElement>(null);
  const stepRef = useRef<HTMLInputElement>(null);
  const [menu, setMenu] = useState(false);
  const close = () => setMenu(false);

  const rename = () => {
    const next = window.prompt("Nombre del proyecto:", doc?.name ?? "");
    if (next && next.trim()) {
      import("../api").then(({ api }) =>
        api.renameProject(next.trim()).then(adoptScene).catch((e) => setError(String(e))),
      );
    }
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

      <button className="icon-btn" disabled={!doc?.can_undo || busy} onClick={() => void undo()} title="Deshacer">
        <Undo2 size={16} />
      </button>
      <button className="icon-btn" disabled={!doc?.can_redo || busy} onClick={() => void redo()} title="Rehacer">
        <Redo2 size={16} />
      </button>

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
