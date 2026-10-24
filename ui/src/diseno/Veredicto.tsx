import type { ReactNode } from "react";
import IconoSeveridad from "./IconoSeveridad";
import type { Severidad } from "./atencion";
import "./diseno.css";

/* El veredicto arriba de un panel (plan V8.5 D13–D14): UNA frase que contesta la pregunta del
   panel («El tablero cumple», «1 cosa por corregir y 2 por revisar»), con su ícono. Debajo, a
   lo sumo una nota corta (qué se revisó). La frase se arma con `veredictoDe` (atencion.ts).
   `aria-live`: si cambia mientras el panel está abierto, el lector lo anuncia. */

interface Props {
  severidad: Severidad;
  frase: string;
  /** Una nota corta bajo la frase: «Revisamos 12 reglas». */
  nota?: ReactNode;
}

export default function Veredicto({ severidad, frase, nota }: Props) {
  return (
    <div className={`veredicto sev-${severidad}`} aria-live="polite">
      <IconoSeveridad severidad={severidad} tamano={20} />
      <div className="vd-texto">
        <p className="vd-frase">{frase}</p>
        {nota && <p className="vd-nota">{nota}</p>}
      </div>
    </div>
  );
}
