import { Check, X } from "lucide-react";
import { useStore } from "../state/store";
import Spinner from "../ui/Spinner";
import { useVisor } from "./estado";
import { avisoVisible } from "./textoAviso";
import "./aviso.css";

/* Aviso del agente, arriba al centro del visor (plan modo-visor). Sólo existe en el visor (lo
   monta `CapaVisor`); el contorno verde, en cambio, vale en los dos modos.
   - Mientras corre un lote del agente: «El agente está trabajando…» con spinner y sin botones
     (D10; el estado lo lleva `trabajando.ts`). Gana a un aviso de cambios viejo.
   - Al terminar, cuando llega el refresco: «El agente cambió N piezas» (D8). «Ver» encuadra las
     piezas marcadas que sigan en la escena y vuelve a pulsar su contorno; × cierra el aviso y
     deja el punto del árbol. Sin «Deshacer» (D9): deshacer revierte el último lote, y un aviso
     puede juntar dos lotes del agente. */

export default function AvisoAgente() {
  const aviso = useVisor((s) => s.aviso);
  const trabajando = useVisor((s) => s.trabajando);
  // la barra de selección del visor ocupa arriba al centro: el aviso va debajo (como el mockup)
  const bajoSeleccion = useStore((s) => s.selection.length > 0 && s.pickRequest === null);
  const visible = avisoVisible(trabajando, aviso);
  if (!visible) return null;
  const enCurso = visible.tipo === "trabajando";
  const hayQueVer = !enCurso && !!aviso && aviso.nuevos.length + aviso.cambiados.length > 0;

  const ver = () => {
    const enEscena = new Set((useStore.getState().scene?.features ?? []).map((f) => f.id));
    const ids = useVisor.getState().marcados.filter((id) => enEscena.has(id));
    window.dispatchEvent(new CustomEvent("apolo:fit", { detail: { ids } }));
    useVisor.getState().repulsar();
  };

  return (
    <div
      className={`aviso-agente${enCurso ? " en-curso" : ""}${bajoSeleccion ? " bajo-seleccion" : ""}`}
      role="status"
    >
      <span className={enCurso ? "aviso-curso" : "aviso-ok"} aria-hidden>
        {enCurso ? <Spinner size={14} /> : <Check size={14} />}
      </span>
      <span className="aviso-texto">{visible.texto}</span>
      {hayQueVer && (
        <button type="button" className="primary" onClick={ver}>
          Ver
        </button>
      )}
      {!enCurso && (
        <button
          type="button"
          className="aviso-cerrar"
          aria-label="Cerrar aviso"
          title="Cerrar aviso"
          onClick={() => useVisor.getState().descartarAviso()}
        >
          <X size={15} />
        </button>
      )}
    </div>
  );
}
