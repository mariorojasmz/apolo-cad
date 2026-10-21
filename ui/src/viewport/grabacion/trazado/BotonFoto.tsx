import { createPortal } from "react-dom";
import { Camera, X } from "lucide-react";
import { create } from "zustand";
import { useStore } from "../../../state/store";
import { useGrabacion } from "../BotonGrabar";
import { GrabacionCancelada } from "../reloj";
import { fotoRegistrada } from "./foto";
import { nombreFoto } from "./nivel";
import "../grabacion.css";

/* «Foto realista» del visor (plan video-realista, D6): traza lo que se ve con el nivel máximo y
   descarga el PNG. Tarda (minutos en una GPU integrada): el aviso dice el avance y deja cancelar.
   Estado en su propia store: el botón está en las dos barras del visor y sólo una se monta. */

type Estado =
  | { fase: "quieta" }
  | { fase: "preparando" }
  | { fase: "trazando"; hechas: number; total: number }
  | { fase: "lista"; archivo: string; segundos: number }
  | { fase: "error"; mensaje: string };

interface FotoEstado {
  estado: Estado;
  cancelar: boolean;
  set: (e: Estado) => void;
}

export const useFoto = create<FotoEstado>((set) => ({
  estado: { fase: "quieta" },
  cancelar: false,
  set: (estado) => set({ estado }),
}));

export const fotoOcupada = (e: Estado) => e.fase === "preparando" || e.fase === "trazando";

function descargar(png: Blob, archivo: string): void {
  const url = URL.createObjectURL(png);
  const a = document.createElement("a");
  a.href = url;
  a.download = archivo;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function sacarFotoRealista(): Promise<void> {
  const f = useFoto.getState();
  const foto = fotoRegistrada();
  if (fotoOcupada(f.estado) || !foto) return;
  useFoto.setState({ cancelar: false });
  f.set({ fase: "preparando" });
  try {
    const r = await foto({
      cancelado: () => useFoto.getState().cancelar,
      progreso: (hechas, total) => f.set({ fase: "trazando", hechas, total }),
    });
    const archivo = nombreFoto(useStore.getState().scene?.document.name ?? null);
    descargar(r.png, archivo);
    f.set({ fase: "lista", archivo, segundos: r.segundos });
  } catch (e) {
    f.set({ fase: "error", mensaje: e instanceof GrabacionCancelada ? "Cancelaste la foto."
      : `No pudimos sacar la foto: ${e instanceof Error ? e.message : String(e)}` });
  }
}

const tiempo = (s: number) => (s < 90 ? `${Math.round(s)} s` : `${Math.round(s / 60)} min`);

function Aviso() {
  const e = useFoto((s) => s.estado);
  if (e.fase === "quieta") return null;
  const cerrar = () => useFoto.getState().set({ fase: "quieta" });
  return createPortal(
    <div className="aviso-grabacion" role="status">
      {e.fase === "preparando" && <span>Preparando la foto realista…</span>}
      {e.fase === "trazando" && (
        <>
          <span>Trazando la foto: {e.hechas} de {e.total} muestras</span>
          <button type="button" onClick={() => useFoto.setState({ cancelar: true })}>Cancelar</button>
        </>
      )}
      {(e.fase === "lista" || e.fase === "error") && (
        <>
          <span>{e.fase === "lista" ? `La foto está lista (${tiempo(e.segundos)}): la bajamos como ${e.archivo}.`
            : e.mensaje}</span>
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
export default function BotonFoto(p: { redondo?: boolean }) {
  const e = useFoto((s) => s.estado);
  const grabando = useGrabacion((s) => s.estado.fase !== "quieta" && s.estado.fase !== "lista"
    && s.estado.fase !== "error");
  const activo = fotoOcupada(e);
  return (
    <>
      {p.redondo ? (
        <button type="button" className={`rb${activo ? " on" : ""}`} title="Foto realista"
          aria-label="Foto realista" disabled={activo || grabando} onClick={() => void sacarFotoRealista()}>
          <Camera size={17} />
        </button>
      ) : (
        <button type="button" className={activo ? "active" : ""} disabled={activo || grabando}
          onClick={() => void sacarFotoRealista()}>
          Foto realista
        </button>
      )}
      <Aviso />
    </>
  );
}
