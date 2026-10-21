import { createPortal } from "react-dom";
import { Video, X } from "lucide-react";
import { create } from "zustand";
import VerDetalle from "../../ui/VerDetalle";
import { abrirConGuion } from "./grabador";
import { grabador } from "./registro";
import { GrabacionCancelada } from "./reloj";
import { fotoEnCurso } from "./trazado/foto";
import "./grabacion.css";

/* «Grabar video» del visor (plan video-realista, F3 · D7): graba a la vista el mismo video que
   `publicar generar --render navegador` —el guion de montaje del proyecto, con la máquina
   andando si ya se simuló— y la API lo deja en su carpeta de grabaciones. Mientras graba, el 3D
   muestra cada cuadro; el aviso dice el avance y deja cancelar. El estado vive en su propia store:
   el botón está en las dos barras del visor y sólo una se monta a la vez. */

type Estado =
  | { fase: "quieta" }
  | { fase: "preparando" }
  | { fase: "grabando"; hechos: number; total: number }
  | { fase: "armando" }
  | { fase: "lista"; video: string; segundos: number }
  | { fase: "error"; mensaje: string };

interface Grabacion {
  estado: Estado;
  cancelar: boolean;
  set: (e: Estado) => void;
}

export const useGrabacion = create<Grabacion>((set) => ({
  estado: { fase: "quieta" },
  cancelar: false,
  set: (estado) => set({ estado }),
}));

const ocupada = (e: Estado) => e.fase === "preparando" || e.fase === "grabando" || e.fase === "armando";

export async function grabarDesdeElVisor(): Promise<void> {
  const g = useGrabacion.getState();
  const grabar = grabador();
  if (ocupada(g.estado) || !grabar || fotoEnCurso()) return; // la foto realista usa el mismo modo
  useGrabacion.setState({ cancelar: false });
  g.set({ fase: "preparando" });
  try {
    const apertura = await abrirConGuion();
    const r = await grabar(apertura, {
      cancelado: () => useGrabacion.getState().cancelar,
      progreso: ({ subidos, total }) => g.set(subidos >= total ? { fase: "armando" }
        : { fase: "grabando", hechos: subidos, total }),
    });
    g.set({ fase: "lista", video: r.informe.video, segundos: r.segundosTotal });
  } catch (e) {
    g.set({ fase: "error", mensaje: e instanceof GrabacionCancelada ? "Cancelaste la grabación."
      : `No pudimos grabar el video: ${e instanceof Error ? e.message : String(e)}` });
  }
}

const minutos = (s: number) => (s < 90 ? `${Math.round(s)} s` : `${Math.round(s / 60)} min`);

function Aviso() {
  const e = useGrabacion((s) => s.estado);
  if (e.fase === "quieta") return null;
  const cerrar = () => useGrabacion.getState().set({ fase: "quieta" });
  return createPortal(
    <div className="aviso-grabacion" role="status">
      {e.fase === "preparando" && <span>Preparando el video…</span>}
      {e.fase === "grabando" && (
        <>
          <span>Grabando el video: {e.hechos} de {e.total} cuadros</span>
          <button type="button" onClick={() => useGrabacion.setState({ cancelar: true })}>Cancelar</button>
        </>
      )}
      {e.fase === "armando" && <span>Armando el video…</span>}
      {(e.fase === "lista" || e.fase === "error") && (
        <>
          <div className="ag-texto">
            <span>{e.fase === "lista" ? `El video está listo (${minutos(e.segundos)}).` : e.mensaje}</span>
            {e.fase === "lista" && (
              <VerDetalle resumen="Dónde quedó">
                <code>{e.video}</code>
              </VerDetalle>
            )}
          </div>
          <button type="button" className="ag-cerrar" onClick={cerrar} aria-label="Cerrar el aviso" title="Cerrar el aviso">
            <X size={14} />
          </button>
        </>
      )}
    </div>,
    document.body,
  );
}

/** El botón (redondo en el visor, con texto en Completo) y su aviso. */
export default function BotonGrabar(p: { redondo?: boolean }) {
  const e = useGrabacion((s) => s.estado);
  const activo = ocupada(e);
  return (
    <>
      {p.redondo ? (
        <button type="button" className={`rb${activo ? " on" : ""}`} title="Grabar video"
          aria-label="Grabar video" disabled={activo} onClick={() => void grabarDesdeElVisor()}>
          <Video size={17} />
        </button>
      ) : (
        <button type="button" className={activo ? "active" : ""} disabled={activo}
          onClick={() => void grabarDesdeElVisor()}>
          Grabar video
        </button>
      )}
      <Aviso />
    </>
  );
}
