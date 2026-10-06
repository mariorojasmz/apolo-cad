import { useEffect, useRef, useState } from "react";
import { Check, ClipboardCopy, Copy, Crop, EyeOff, Focus, Scan, Trash2 } from "lucide-react";
import { useStore } from "../state/store";
import { copiarAlPortapapeles, referenciaParaAgente } from "../visor/copiar";

/* Barra de la selección (abajo al centro): nombre y acciones rápidas sobre las piezas
   elegidas. Las acciones van directo a la store; encuadrar llega por props porque mueve la
   cámara de Viewport. Salió de Viewport.tsx para hacerle lugar bajo el trinquete de tamaño
   (plan modo-visor, D12). En el visor (D6) va arriba al centro, sin Duplicar ni Eliminar (lo
   destructivo queda en Completo; los atajos no cambian) y con «Copiar para el agente». */

interface Props {
  /** Nombre de la pieza, o «N sólidos» con varias; vacío si no se resolvió. */
  nombre: string;
  cantidad: number;
  /** Ids seleccionados (el visor copia el de una pieza sola). */
  ids: string[];
  onCentrar: () => void;
  /** Variante del modo Visor (`visor/estado.ts`). */
  visor: boolean;
}

export default function BarraSeleccion({ nombre, cantidad, ids, onCentrar, visor }: Props) {
  if (visor) return <SeleccionVisor nombre={nombre} ids={ids} onCentrar={onCentrar} />;
  return (
    <div className="selection-bar">
      <span className="sb-count">{nombre || `${cantidad} sólidos`}</span>
      <span className="overlay-sep" />
      <button title="Duplicar (Ctrl+D)" onClick={() => void useStore.getState().duplicateSelection()}>
        <Copy size={15} />
      </button>
      <button title="Ocultar (H)" onClick={() => void useStore.getState().hideSelection()}>
        <EyeOff size={15} />
      </button>
      <button title="Aislar (I)" onClick={() => void useStore.getState().isolate()}>
        <Focus size={15} />
      </button>
      <button title="Centrar (F)" onClick={onCentrar}>
        <Crop size={15} />
      </button>
      <span className="overlay-sep" />
      <button className="danger" title="Eliminar (Supr)" onClick={() => void useStore.getState().deleteSelection()}>
        <Trash2 size={15} />
      </button>
    </div>
  );
}

/** «sin copiar» | «copiado» (~2 s) | el texto, si el portapapeles falló (para copiarlo a mano). */
type Copia = null | "ok" | { aMano: string };

function SeleccionVisor({ nombre, ids, onCentrar }: { nombre: string; ids: string[]; onCentrar: () => void }) {
  const una = ids.length === 1;
  const id = una ? ids[0] : "";
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

  return (
    <div className="selection-bar visor" role="toolbar" aria-label="Selección">
      <span className="sb-count">{una ? nombre || id : `${ids.length} piezas`}</span>
      <span className="overlay-sep" />
      <button type="button" onClick={onCentrar}>
        <Scan size={15} /> Encuadrar
      </button>
      <button type="button" onClick={() => void useStore.getState().isolate()}>
        <Focus size={15} /> Aislar
      </button>
      <button type="button" onClick={() => void useStore.getState().hideSelection()}>
        <EyeOff size={15} /> Ocultar
      </button>
      {una && (
        <>
          <span className="overlay-sep" />
          {copia && copia !== "ok" ? (
            <input
              className="sb-a-mano"
              readOnly
              autoFocus
              value={copia.aMano}
              aria-label="Copia este texto para el agente"
              onFocus={(e) => e.target.select()}
            />
          ) : (
            <button type="button" className="sb-copiar" onClick={() => void copiar()}>
              {copia === "ok" ? <Check size={15} /> : <ClipboardCopy size={15} />}
              {copia === "ok" ? "Copiado" : "Copiar para el agente"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
