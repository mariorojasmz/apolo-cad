import { AlertTriangle } from "lucide-react";
import { useStore } from "../state/store";

/* Avisos de robustez del documento (V6.1): el backend avisa si el autoguardado no llega al
   disco o si abrió un proyecto suprimiendo comandos rotos (schema drift). Los muestra la
   StatusBar en Completo y la capa del visor, que no monta la StatusBar (plan modo-visor F3).
   Sin nada que avisar, no pinta nada. */

interface Props {
  /** Clase de un contenedor propio (el visor lo ubica flotando); sin ella, van sueltos. */
  envoltura?: string;
}

export default function AvisosDocumento({ envoltura }: Props) {
  const autosaveFailed = useStore((s) => s.scene?.document.autosave_failed ?? null);
  const suppressed = useStore((s) => s.scene?.document.suppressed_commands?.length ?? 0);
  if (!autosaveFailed && suppressed === 0) return null;

  const avisos = (
    <>
      {autosaveFailed && (
        <span
          className="busy-badge"
          role="status"
          style={{ color: "#d8703a" }}
          title={`El autoguardado falló: ${autosaveFailed}. Tus cambios están en memoria pero NO en disco.`}
        >
          <AlertTriangle size={13} strokeWidth={1.9} /> Sin guardar
        </span>
      )}
      {suppressed > 0 && (
        <span
          className="busy-badge"
          style={{ color: "#d8703a" }}
          title={`Se abrió el proyecto suprimiendo ${suppressed} comando(s) inválido(s). Revísalos en el Historial.`}
        >
          <AlertTriangle size={13} strokeWidth={1.9} /> {suppressed} suprimido{suppressed > 1 ? "s" : ""}
        </span>
      )}
    </>
  );
  return envoltura ? <div className={envoltura}>{avisos}</div> : avisos;
}
