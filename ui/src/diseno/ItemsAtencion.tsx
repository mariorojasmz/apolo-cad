import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import IconoSeveridad from "./IconoSeveridad";
import { ordenarItems, ROTULO_SEVERIDAD, type ItemAtencion } from "./atencion";
import "./diseno.css";

/* La lista de lo que pide atención, bajo el `<Veredicto>` (plan V8.5 D13): cada fila es una
   frase y su cifra, lo más grave primero. Con acción, la fila entera es un botón (clic → la
   cámara vuela a la pieza, o se abre su detalle). Sin cajas ni bordes: la jerarquía la dan el
   peso y el tamaño del texto (D14). La fila `elegida` queda marcada y lleva `debajo` lo que se
   abrió con su clic, pegado a ella (revisión a ciegas de F3b: suelto al final se leía como del
   último ítem). La columna de la cifra se reserva aunque no haya cifra: las flechas alinean. */

interface Props {
  items: readonly ItemAtencion[];
  /** Para el lector de pantalla: «Lo que pide atención en el tablero». */
  rotulo: string;
  /** La clave de la fila elegida. */
  elegida?: string | null;
  /** Lo que se muestra bajo la fila elegida (una frase, un detalle). */
  debajo?: ReactNode;
}

export default function ItemsAtencion({ items, rotulo, elegida, debajo }: Props) {
  if (!items.length) return null;
  return (
    <ul className="items-atencion" aria-label={rotulo}>
      {ordenarItems(items).map((it) => {
        const esta = elegida === it.clave;
        return (
          <li key={it.clave}>
            {it.accion ? (
              <button type="button" className={`ia-fila${esta ? " elegida" : ""}`} onClick={it.accion}
                aria-expanded={esta && !!debajo ? true : undefined}
                aria-label={`${ROTULO_SEVERIDAD[it.severidad]}: ${it.frase}${it.cifra ? `, ${it.cifra}` : ""}`}>
                <Contenido it={it} />
                <ChevronRight className="ia-ir" size={14} aria-hidden="true" />
              </button>
            ) : (
              <div className="ia-fila">
                <Contenido it={it} />
              </div>
            )}
            {esta && debajo && <div className="ia-debajo">{debajo}</div>}
          </li>
        );
      })}
    </ul>
  );
}

function Contenido({ it }: { it: ItemAtencion }) {
  return (
    <>
      <IconoSeveridad severidad={it.severidad} tamano={15} />
      <span className="ia-frase">{it.frase}</span>
      <span className="ia-cifra">{it.cifra ?? ""}</span>
    </>
  );
}
