import { useId, useState, type ReactNode } from "react";
import { Info } from "lucide-react";

/* Ayuda (N2 de ui/CLAUDE.md § Texto y ayuda): la ⓘ junto a una palabra contesta «¿qué
   significa esto?», a pedido. Tres reglas que no se negocian:
   - `type="button"`: dentro de un <form> un botón sin tipo es submit y ejecutaría el comando.
   - El texto se abre EN EL FLUJO (un bloque `role="note"`), no flota: en los paneles de
     Dockview con `overflow` un globo se cortaría.
   - Nunca dentro de un `<label>`: se comería el clic del control. Va de hermano.
   Devuelve el botón y, abierto, el bloque; en una fila flex (`.campo-cabeza`) el bloque baja
   a su propia línea, al final de la fila (`order` + ancho completo en styles.css). */

interface Props {
  /** De qué es la ayuda: el rótulo al que acompaña («Profundidad»). */
  tema: string;
  children: ReactNode;
}

export default function Ayuda({ tema, children }: Props) {
  const [abierta, setAbierta] = useState(false);
  const id = useId();
  return (
    <>
      <button
        type="button"
        className={`ayuda-btn${abierta ? " abierta" : ""}`}
        aria-label={`Ayuda sobre «${tema}»`}
        aria-expanded={abierta}
        aria-controls={abierta ? id : undefined}
        onClick={() => setAbierta((a) => !a)}
      >
        <Info size={12} strokeWidth={2} aria-hidden="true" />
      </button>
      {abierta && (
        <div id={id} role="note" className="ayuda-nota">
          {children}
        </div>
      )}
    </>
  );
}
