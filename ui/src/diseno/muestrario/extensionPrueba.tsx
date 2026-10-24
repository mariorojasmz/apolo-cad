/// <reference types="vite/client" />
import { FileText } from "lucide-react";
import type { Extension } from "../../extensiones/tipos";
import LAMINA from "./lamina-prueba.svg?raw";

/* Una extensión de PRUEBA de la UI con un panel ancho (plan puntos-de-extension-entregables, D7):
   muestra en línea la lámina de esquema que la extensión falsa de la suite de Python dibuja con
   los trazos del núcleo (`tests/ext_prueba/esquema.py`; un test exige que este SVG esté al día).
   Vive en el muestrario, no en `src/extensiones/`: el núcleo publica el registro vacío. */

export function PanelLamina() {
  return (
    <div className="lp-panel">
      <div className="lp-hoja" role="img" aria-label="Esquema de prueba, lámina 1 de 1"
        dangerouslySetInnerHTML={{ __html: LAMINA }} />
    </div>
  );
}

export const EXTENSION_PRUEBA: Extension = {
  nombre: "prueba",
  paneles: [
    { id: "prueba.lamina", titulo: "Esquema de prueba", rotulo: "Esquema", Componente: PanelLamina, icono: FileText,
      ancho: "lamina" },
  ],
};
