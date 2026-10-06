import { useEffect, useMemo, useRef, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import { api } from "../api";
import { useStore } from "../state/store";
import type { ProjectInfo, RevisionInfo } from "../types";
import Spinner from "../ui/Spinner";
import FilaProyecto from "../inicio/FilaProyecto";
import NuevoProyecto from "../inicio/NuevoProyecto";
import Revisiones from "../inicio/Revisiones";
import { agrupar, filtrarYOrdenar, palabras, type Orden } from "../inicio/proyectos";
import "../inicio/inicio.css";

/* Pantalla de proyectos: buscar y abrir uno (lo más frecuente, arriba y con el foco), crear
   uno nuevo y, a la derecha, las revisiones del proyecto abierto. Si la API todavía está
   arrancando (abre y regenera el proyecto reciente antes de atender), la lista no se da por
   vacía: avisa y reintenta sola. */

type Carga = "cargando" | "listo" | "arrancando" | "sin-conexion";

const REINTENTO_MS = 2000;
const MAX_REINTENTOS = 45; // ~90 s: más que un arranque lento con el proyecto reciente

export default function HomeScreen() {
  const show = useStore((s) => s.showHome);
  const openHome = useStore((s) => s.openHome);
  const doc = useStore((s) => s.scene?.document);
  const busy = useStore((s) => s.busy);
  const createProject = useStore((s) => s.createProject);
  const openProjectById = useStore((s) => s.openProjectById);
  const deleteProject = useStore((s) => s.deleteProject);
  const duplicateProject = useStore((s) => s.duplicateProject);
  const saveRevision = useStore((s) => s.saveRevision);
  const restoreRevision = useStore((s) => s.restoreRevision);
  const currentId = doc?.project_id ?? null;

  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [revisions, setRevisions] = useState<RevisionInfo[]>([]);
  const [carga, setCarga] = useState<Carga>("cargando");
  const [intento, setIntento] = useState(0); // «Reintentar» a mano vuelve a empezar el ciclo
  const [consulta, setConsulta] = useState("");
  const [orden, setOrden] = useState<Orden>("recientes");
  const [creando, setCreando] = useState(false);
  const buscador = useRef<HTMLInputElement>(null);

  const recargar = async (): Promise<void> => {
    const [p, r] = await Promise.allSettled([api.projects(), api.revisions()]);
    if (p.status === "rejected") throw p.reason;
    setProjects(p.value);
    setRevisions(r.status === "fulfilled" ? r.value : []);
    setCarga("listo");
  };

  useEffect(() => {
    if (!show) return;
    let vivo = true;
    let veces = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const pedir = () => {
      recargar().catch(() => {
        if (!vivo) return;
        veces += 1;
        if (veces > MAX_REINTENTOS) return setCarga("sin-conexion");
        setCarga("arrancando");
        timer = setTimeout(pedir, REINTENTO_MS);
      });
    };
    setCarga((c) => (c === "listo" ? c : "cargando"));
    pedir();
    return () => {
      vivo = false;
      clearTimeout(timer);
    };
  }, [show, intento]);

  // Esc: primero limpia la búsqueda; después vuelve al modelado (si hay un proyecto abierto)
  useEffect(() => {
    if (!show) return;
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (consulta) setConsulta("");
      else if (currentId !== null) openHome(false);
    };
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
  }, [show, consulta, currentId, openHome]);

  const visibles = useMemo(() => filtrarYOrdenar(projects, consulta, orden), [projects, consulta, orden]);
  const buscadas = useMemo(() => palabras(consulta), [consulta]);
  const grupos = useMemo(
    () => agrupar(visibles, currentId, orden === "recientes" && !buscadas.length),
    [visibles, currentId, orden, buscadas],
  );

  if (!show) return null;

  // Las acciones del store ya muestran el indicador global y publican errores en el toast;
  // aquí sólo se recarga la lista tras las que NO cierran la pantalla.
  const despues = async (p: Promise<unknown>) => {
    await p;
    await recargar().catch(() => undefined);
  };
  const abrir = (p: ProjectInfo) => (p.id === currentId ? openHome(false) : void openProjectById(p.id));
  const restaurar = async (r: RevisionInfo, guardarAntes: boolean) => {
    if (guardarAntes) {
      const nota = r.note.trim();
      await saveRevision(`Antes de restaurar «${nota.length > 60 ? `${nota.slice(0, 60)}…` : nota || "sin nota"}»`);
    }
    await restoreRevision(r.id);
  };

  return (
    <div className="modal-backdrop">
      <div className="modal inicio" role="dialog" aria-label="Proyectos" onClick={(e) => e.stopPropagation()}>
        <header className="inicio-cab">
          <div className="inicio-fila">
            <h3>Proyectos</h3>
            <button className="primary inicio-nuevo" disabled={busy} onClick={() => setCreando(true)}>
              <Plus size={15} /> Nuevo proyecto
            </button>
            {currentId !== null && (
              <button className="ghost" onClick={() => openHome(false)}>
                <X size={15} /> Volver al modelado
              </button>
            )}
          </div>
          <div className="inicio-fila">
            <label className="inicio-buscar">
              <Search size={15} aria-hidden />
              <input
                ref={buscador}
                autoFocus
                placeholder="Buscar proyecto, p. ej. «faja 4m»"
                value={consulta}
                onChange={(e) => setConsulta(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && visibles[0]) abrir(visibles[0]);
                }}
              />
              {consulta && (
                <button className="icono" aria-label="Limpiar búsqueda" onClick={() => { setConsulta(""); buscador.current?.focus(); }}>
                  <X size={14} />
                </button>
              )}
            </label>
            <div className="inicio-orden" role="group" aria-label="Ordenar">
              <button className={orden === "recientes" ? "on" : ""} aria-pressed={orden === "recientes"} onClick={() => setOrden("recientes")}>
                Recientes
              </button>
              <button className={orden === "nombre" ? "on" : ""} aria-pressed={orden === "nombre"} onClick={() => setOrden("nombre")}>
                Nombre
              </button>
            </div>
            {carga === "listo" && (
              <span className="inicio-cuenta">
                {buscadas.length ? `${visibles.length} de ${projects.length}` : `${projects.length} proyectos`}
              </span>
            )}
          </div>
        </header>

        <div className="inicio-cuerpo">
          <section className="inicio-lista" aria-label="Lista de proyectos">
            {creando && (
              <NuevoProyecto
                ocupado={busy}
                onCancelar={() => setCreando(false)}
                onCrear={(nombre, plantilla) => void createProject(nombre, plantilla)}
              />
            )}

            {carga === "cargando" && <p className="inicio-estado"><Spinner size={15} /> Cargando proyectos…</p>}
            {carga === "arrancando" && (
              <p className="inicio-estado"><Spinner size={15} /> Apolo está arrancando. Tus proyectos aparecen en unos segundos.</p>
            )}
            {carga === "sin-conexion" && (
              <div className="inicio-estado error">
                <p>No pudimos conectar con el servidor de Apolo. Revisa que esté abierto.</p>
                <button onClick={() => setIntento((n) => n + 1)}>Reintentar</button>
              </div>
            )}

            {carga === "listo" && !projects.length && (
              <div className="inicio-estado">
                <p>Aquí van a aparecer tus proyectos. Crea el primero para empezar.</p>
                <button className="primary" onClick={() => setCreando(true)}>Crear proyecto</button>
              </div>
            )}
            {carga === "listo" && projects.length > 0 && !visibles.length && (
              <div className="inicio-estado">
                <p>Ningún proyecto se llama así.</p>
                <button className="ghost" onClick={() => setConsulta("")}>Ver todos</button>
              </div>
            )}

            {carga === "listo" &&
              grupos.map((g) => (
                <div key={g.titulo ?? "todos"} className="inicio-grupo">
                  {g.titulo && <h5>{g.titulo}</h5>}
                  <ul>
                    {g.proyectos.map((p) => (
                      <FilaProyecto
                        key={p.id}
                        proyecto={p}
                        abierto={p.id === currentId}
                        buscadas={buscadas}
                        ocupado={busy}
                        onAbrir={() => abrir(p)}
                        onDuplicar={() => void despues(duplicateProject(p.id))}
                        onEliminar={() => void despues(deleteProject(p.id))}
                      />
                    ))}
                  </ul>
                </div>
              ))}
          </section>

          <Revisiones
            proyecto={currentId !== null ? doc?.name ?? null : null}
            cargadas={carga === "listo"}
            revisiones={revisions}
            ocupado={busy}
            onGuardar={(nota) => despues(saveRevision(nota))}
            onRestaurar={(r, guardarAntes) => void restaurar(r, guardarAntes)}
          />
        </div>
      </div>
    </div>
  );
}
