/* Capa del modo Visor: ocupa la misma celda del grid que el dock (`.apolo-dock`), encima del
   3D maximizado, y deja pasar los clics al canvas (`pointer-events: none`; cada hijo vuelve a
   `auto`). Se monta SÓLO en el visor (App.tsx); su CSS está en `visor.css`.
   Plan modo-visor: F3 monta aquí los cajones (Árbol a la izquierda, un panel a la derecha), la
   barra de paneles y la ficha de pieza; F4, el aviso de los cambios del agente. */
import AvisoAgente from "./AvisoAgente";

export default function CapaVisor() {
  return <div className="capa-visor"><AvisoAgente /></div>;
}
