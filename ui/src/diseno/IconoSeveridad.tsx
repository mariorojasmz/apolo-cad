import { CircleAlert, CircleCheck, CircleDashed, TriangleAlert } from "lucide-react";
import { ROTULO_SEVERIDAD, type Severidad } from "./atencion";
import "./diseno.css";

/* El ícono de una severidad (plan V8.5 D14): forma Y color del tema, nunca sólo color, y su
   rótulo para el lector de pantalla. Vive en el PANEL; el 3D no lleva tintes de estado. */

const ICONO = { falla: CircleAlert, aviso: TriangleAlert, sin_evaluar: CircleDashed, bien: CircleCheck };

export default function IconoSeveridad({ severidad, tamano = 16 }: { severidad: Severidad; tamano?: number }) {
  const Icono = ICONO[severidad];
  return (
    <span className={`icono-severidad sev-${severidad}`} role="img" aria-label={ROTULO_SEVERIDAD[severidad]}>
      <Icono size={tamano} strokeWidth={2} aria-hidden="true" />
    </span>
  );
}
