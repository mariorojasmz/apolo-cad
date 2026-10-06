import { Copy, Crop, EyeOff, Focus, Trash2 } from "lucide-react";
import { useStore } from "../state/store";

/* Barra de la selección (abajo al centro): nombre y acciones rápidas sobre las piezas
   elegidas. Las acciones van directo a la store; encuadrar llega por props porque mueve la
   cámara de Viewport. Salió de Viewport.tsx para hacerle lugar bajo el trinquete de tamaño
   (plan modo-visor, D12). */

interface Props {
  /** Nombre de la pieza, o «N sólidos» con varias; vacío si no se resolvió. */
  nombre: string;
  cantidad: number;
  onCentrar: () => void;
}

export default function BarraSeleccion({ nombre, cantidad, onCentrar }: Props) {
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
