import type { ReactNode } from "react";
import { X } from "lucide-react";
import type { AnchoPanel } from "../extensiones/tipos";
import { claseCajon, type Lado } from "./cajones";
import "./cajones.css";

/** Un cajón del visor sin estado: cabecera con el título y Cerrar, y el cuerpo. Lo arma `Cajon`
   con el panel abierto y el muestrario con un panel de extensión de prueba (`ancho: "lamina"`),
   sin cargar los paneles ni el store de la app. */
export default function MarcoCajon({ lado, titulo, ancho, onCerrar, children }: {
  lado: Lado; titulo: string; ancho?: AnchoPanel; onCerrar: () => void; children: ReactNode;
}) {
  return (
    <aside className={claseCajon(lado, ancho)} aria-label={titulo}>
      <header className="cajon-cabecera">
        <h2>{titulo}</h2>
        <button
          type="button"
          className="cajon-cerrar"
          title="Cerrar"
          aria-label={`Cerrar ${titulo}`}
          onClick={onCerrar}
        >
          <X size={16} />
        </button>
      </header>
      <div className="cajon-cuerpo">{children}</div>
    </aside>
  );
}
