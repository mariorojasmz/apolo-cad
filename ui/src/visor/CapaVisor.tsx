import AvisosDocumento from "../panels/AvisosDocumento";
import AvisoAgente from "./AvisoAgente";
import BarraPaneles from "./BarraPaneles";
import Cajones from "./Cajon";
import ChipOcultas from "./ChipOcultas";
import FichaPieza from "./FichaPieza";

/* Capa del modo Visor: ocupa la misma celda del grid que el dock (`.apolo-dock`), encima del
   3D maximizado, y deja pasar los clics al canvas (`pointer-events: none`; cada hijo vuelve a
   `auto`). Se monta SÓLO en el visor (App.tsx); su CSS está en `visor.css`.
   Plan modo-visor: F3 monta aquí los cajones (Árbol a la izquierda, un panel a la derecha), la
   barra de paneles, la ficha de pieza y los avisos del documento que en Completo muestra la
   StatusBar (CSS en `cajones.css`); F4, el aviso de los cambios del agente (`aviso.css`).
   `ChipOcultas` (arriba a la izquierda) es la vuelta de Ocultar y Aislar: sin árbol a la vista,
   una pieza oculta no tenía por dónde volver. */

export default function CapaVisor() {
  return (
    <div className="capa-visor">
      <Cajones />
      <FichaPieza />
      <BarraPaneles />
      <AvisosDocumento envoltura="avisos-visor" />
      <AvisoAgente />
      <ChipOcultas />
    </div>
  );
}
