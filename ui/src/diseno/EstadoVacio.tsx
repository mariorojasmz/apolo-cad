import type { ReactNode } from "react";
import "./diseno.css";

/* Estado vacío (ui/CLAUDE.md § Texto y ayuda; plan V8.5 D13): la primera vez en un panel dice
   QUÉ va a aparecer aquí y da la acción para empezar, en vez de un «No hay datos» o un tour.
   Una frase de título y, a lo sumo, una de cómo empezar. */

interface Props {
  /** Un ícono de lucide, decorativo (se oculta al lector). */
  icono?: ReactNode;
  /** Qué va a aparecer aquí: «Aquí vas a ver el tablero armado». */
  titulo: string;
  /** Cómo empezar, en una frase. */
  children?: ReactNode;
  /** El botón que empieza (verbo + objeto). */
  accion?: { rotulo: string; onClick: () => void };
}

export default function EstadoVacio({ icono, titulo, children, accion }: Props) {
  return (
    <div className="estado-vacio">
      {icono && <span className="ev-icono" aria-hidden="true">{icono}</span>}
      <p className="ev-titulo">{titulo}</p>
      {children && <p className="ev-texto">{children}</p>}
      {accion && (
        <button type="button" className="primary ev-accion" onClick={accion.onClick}>
          {accion.rotulo}
        </button>
      )}
    </div>
  );
}
