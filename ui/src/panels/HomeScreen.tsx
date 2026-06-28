import { useEffect, useState } from "react";
import { api } from "../api";
import { useStore } from "../state/store";
import type { ProjectInfo, RevisionInfo } from "../types";

/* Pantalla Inicio: proyectos (SQLite, con autoguardado), plantillas de nuevo
   proyecto y revisiones del proyecto abierto. */

const TEMPLATES = [
  { id: null, label: "Vacío" },
  { id: "transportador", label: "Transportador 2 m (paramétrico)" },
  { id: "brazo", label: "Brazo robótico 4 ejes" },
] as const;

export default function HomeScreen() {
  const show = useStore((s) => s.showHome);
  const openHome = useStore((s) => s.openHome);
  const currentId = useStore((s) => s.scene?.document.project_id ?? null);
  const busy = useStore((s) => s.busy);
  const createProject = useStore((s) => s.createProject);
  const openProjectById = useStore((s) => s.openProjectById);
  const deleteProject = useStore((s) => s.deleteProject);
  const duplicateProject = useStore((s) => s.duplicateProject);
  const saveRevision = useStore((s) => s.saveRevision);
  const restoreRevision = useStore((s) => s.restoreRevision);

  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [revisions, setRevisions] = useState<RevisionInfo[]>([]);
  const [name, setName] = useState("");
  const [template, setTemplate] = useState<string | null>(null);
  const [revNote, setRevNote] = useState("");

  const reload = () => {
    api.projects().then(setProjects).catch(() => setProjects([]));
    api.revisions().then(setRevisions).catch(() => setRevisions([]));
  };

  useEffect(() => {
    if (show) reload();
  }, [show]);

  if (!show) return null;

  // Las acciones del store ya muestran el indicador global (overlay "Abriendo proyecto…" en las
  // pesadas) y publican errores en el toast; aquí solo recargamos la lista tras las que NO cierran
  // la pantalla (borrar/duplicar/guardar revisión). Las de abrir/crear/restaurar cierran Inicio solas.
  const after = async (p: Promise<unknown>) => {
    await p;
    reload();
  };

  return (
    <div className="modal-backdrop">
      <div className="modal modal-home" onClick={(e) => e.stopPropagation()}>
        <div className="home-head">
          <h3>Genix Apolo CAD — Proyectos</h3>
          <button onClick={() => openHome(false)}>Volver al modelado</button>
        </div>

        <div className="home-new">
          <input
            placeholder="Nombre del nuevo proyecto…"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select value={template ?? ""} onChange={(e) => setTemplate(e.target.value || null)}>
            {TEMPLATES.map((t) => (
              <option key={t.label} value={t.id ?? ""}>{t.label}</option>
            ))}
          </select>
          <button
            className="primary"
            disabled={busy}
            onClick={() => void createProject(name.trim() || "Sin título", template)}
          >
            + Crear
          </button>
        </div>

        <div className="home-grid">
          {projects.map((p) => (
            <div key={p.id} className={`home-card ${p.id === currentId ? "current" : ""}`}>
              <strong>{p.name}</strong>
              <span className="hint">
                {p.pieces} piezas · {p.updated_at.replace("T", " ")}
              </span>
              <div className="home-card-actions">
                {p.id === currentId ? (
                  <span className="estado-ok">● abierto</span>
                ) : (
                  <>
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => void openProjectById(p.id)}
                    >
                      Abrir
                    </button>
                    <button
                      className="ghost"
                      disabled={busy}
                      onClick={() => void after(deleteProject(p.id))}
                    >
                      ✕
                    </button>
                  </>
                )}
                <button disabled={busy} onClick={() => void after(duplicateProject(p.id))}>
                  Duplicar
                </button>
              </div>
            </div>
          ))}
          {projects.length === 0 && <p className="hint">Sin proyectos todavía.</p>}
        </div>

        <div className="home-revisions">
          <h4>Revisiones del proyecto abierto</h4>
          <div className="vars-form">
            <input
              placeholder="Nota de la revisión (p. ej. 'antes de cambiar el paso')"
              value={revNote}
              onChange={(e) => setRevNote(e.target.value)}
            />
            <button
              disabled={busy}
              onClick={() => void after(saveRevision(revNote.trim()).then(() => setRevNote("")))}
            >
              💾 Guardar revisión
            </button>
          </div>
          {revisions.length > 0 && (
            <ul className="rev-list">
              {revisions.map((r) => (
                <li key={r.id}>
                  <span>
                    <strong>{r.note}</strong> · {r.pieces} piezas · {r.created_at.replace("T", " ")}
                  </span>
                  <button
                    disabled={busy}
                    title="Vuelve el proyecto a este estado"
                    onClick={() => void restoreRevision(r.id)}
                  >
                    ⟲ Restaurar
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
