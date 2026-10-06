import { useEffect, useRef, useState } from "react";
import { Check, ClipboardCopy } from "lucide-react";
import { copiarAlPortapapeles, referenciaParaAgente } from "./copiar";

/* «Copiar para el agente» (plan modo-visor, D6 y D7): un solo botón para la barra de selección
   y la ficha de pieza, con el mismo «Copiado» y la misma salida si el portapapeles falla. */

/** «sin copiar» | «copiado» (~2 s) | el texto, si el portapapeles falló (para copiarlo a mano). */
type Copia = null | "ok" | { aMano: string };

interface Props {
  /** Nombre de la pieza tal como lo ve la persona. */
  nombre: string;
  id: string;
  className?: string;
  /** Clase del campo de solo lectura que aparece si no se pudo copiar. */
  claseAMano?: string;
  tamIcono?: number;
}

export default function BotonCopiar({ nombre, id, className, claseAMano, tamIcono = 15 }: Props) {
  const [copia, setCopia] = useState<Copia>(null);
  const reloj = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => {
    setCopia(null); // otra pieza: el aviso de la anterior no aplica
    return () => clearTimeout(reloj.current);
  }, [id]);

  const copiar = async () => {
    const texto = referenciaParaAgente(nombre || id, id);
    clearTimeout(reloj.current);
    if (await copiarAlPortapapeles(texto)) {
      setCopia("ok");
      reloj.current = setTimeout(() => setCopia(null), 2000);
    } else setCopia({ aMano: texto });
  };

  if (copia && copia !== "ok")
    return (
      <input
        className={claseAMano}
        readOnly
        autoFocus
        value={copia.aMano}
        aria-label="Copia este texto para el agente"
        onFocus={(e) => e.target.select()}
      />
    );
  return (
    <button type="button" className={className} onClick={() => void copiar()}>
      {copia === "ok" ? <Check size={tamIcono} /> : <ClipboardCopy size={tamIcono} />}
      {copia === "ok" ? "Copiado" : "Copiar para el agente"}
    </button>
  );
}
