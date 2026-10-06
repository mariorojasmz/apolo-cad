import { Copy, Crop, EyeOff, Focus, Scan, Trash2 } from "lucide-react";
import { useStore } from "../state/store";
import BotonCopiar from "../visor/BotonCopiar";

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

function SeleccionVisor({ nombre, ids, onCentrar }: { nombre: string; ids: string[]; onCentrar: () => void }) {
  const una = ids.length === 1;
  const id = una ? ids[0] : "";
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
          <BotonCopiar nombre={nombre} id={id} className="sb-copiar" claseAMano="sb-a-mano" />
        </>
      )}
    </div>
  );
}
