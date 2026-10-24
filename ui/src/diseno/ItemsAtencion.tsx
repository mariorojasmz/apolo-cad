import { ChevronRight } from "lucide-react";
import IconoSeveridad from "./IconoSeveridad";
import { ordenarItems, ROTULO_SEVERIDAD, type ItemAtencion } from "./atencion";
import "./diseno.css";

/* La lista de lo que pide atención, bajo el `<Veredicto>` (plan V8.5 D13): cada fila es una
   frase y su cifra, lo más grave primero. Con acción, la fila entera es un botón (clic → la
   cámara vuela a la pieza, o se abre su detalle). Sin cajas ni bordes: la jerarquía la dan el
   peso y el tamaño del texto (D14). */

interface Props {
  items: readonly ItemAtencion[];
  /** Para el lector de pantalla: «Lo que pide atención en el tablero». */
  rotulo: string;
}

export default function ItemsAtencion({ items, rotulo }: Props) {
  if (!items.length) return null;
  return (
    <ul className="items-atencion" aria-label={rotulo}>
      {ordenarItems(items).map((it) => (
        <li key={it.clave}>
          {it.accion ? (
            <button type="button" className="ia-fila" onClick={it.accion}
              aria-label={`${ROTULO_SEVERIDAD[it.severidad]}: ${it.frase}${it.cifra ? `, ${it.cifra}` : ""}`}>
              <Contenido it={it} />
              <ChevronRight className="ia-ir" size={14} aria-hidden="true" />
            </button>
          ) : (
            <div className="ia-fila">
              <Contenido it={it} />
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function Contenido({ it }: { it: ItemAtencion }) {
  return (
    <>
      <IconoSeveridad severidad={it.severidad} tamano={15} />
      <span className="ia-frase">{it.frase}</span>
      {it.cifra && <span className="ia-cifra">{it.cifra}</span>}
    </>
  );
}
