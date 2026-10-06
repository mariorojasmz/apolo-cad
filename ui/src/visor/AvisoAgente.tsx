import { Check, X } from "lucide-react";
import { useStore } from "../state/store";
import { useVisor } from "./estado";
import { textoAviso } from "./textoAviso";
import "./aviso.css";

/* Aviso «El agente cambió N piezas» (plan modo-visor, D8), arriba al centro del visor. Sólo
   existe en el visor (lo monta `CapaVisor`); el contorno verde, en cambio, vale en los dos
   modos. «Ver» encuadra las piezas marcadas que sigan en la escena y vuelve a pulsar su
   contorno; × cierra el aviso y deja el punto del árbol. Sin «Deshacer» (D9): deshacer
   revierte el último lote, y un aviso puede juntar dos lotes del agente. */

export default function AvisoAgente() {
  const aviso = useVisor((s) => s.aviso);
  // la barra de selección del visor ocupa arriba al centro: el aviso va debajo (como el mockup)
  const bajoSeleccion = useStore((s) => s.selection.length > 0 && s.pickRequest === null);
  if (!aviso) return null;
  const texto = textoAviso(aviso);
  if (!texto) return null;
  const hayQueVer = aviso.nuevos.length + aviso.cambiados.length > 0;

  const ver = () => {
    const enEscena = new Set((useStore.getState().scene?.features ?? []).map((f) => f.id));
    const ids = useVisor.getState().marcados.filter((id) => enEscena.has(id));
    window.dispatchEvent(new CustomEvent("apolo:fit", { detail: { ids } }));
    useVisor.getState().repulsar();
  };

  return (
    <div className={`aviso-agente${bajoSeleccion ? " bajo-seleccion" : ""}`} role="status">
      <span className="aviso-ok" aria-hidden>
        <Check size={14} />
      </span>
      <span className="aviso-texto">{texto}</span>
      {hayQueVer && (
        <button type="button" className="primary" onClick={ver}>
          Ver
        </button>
      )}
      <button
        type="button"
        className="aviso-cerrar"
        aria-label="Cerrar aviso"
        title="Cerrar aviso"
        onClick={() => useVisor.getState().descartarAviso()}
      >
        <X size={15} />
      </button>
    </div>
  );
}
