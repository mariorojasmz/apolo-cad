import { useState } from "react";
import Deslizador from "../diseno/Deslizador";
import ItemsAtencion from "../diseno/ItemsAtencion";
import Veredicto from "../diseno/Veredicto";
import VerDetalle from "../ui/VerDetalle";
import DetalleTablero from "./DetalleTablero";
import type { ItemTablero, PanelTableroOut } from "./tipos";
import { accionPuerta, itemsDeAtencion, type AccionesTablero } from "./vista";
import "./tablero.css";

/* La vista del panel «Tablero» (plan V8.5 D13–D14): responde «¿está bien mi tablero?» arriba
   (un veredicto), debajo sólo lo que pide atención (clic → la cámara vuela y lo muestra), la
   puerta con su deslizador y, a pedido, el detalle. Recibe todo por props: la monta el panel real
   (`PanelTablero.tsx`, con la API y el visor) y el muestrario (datos de ejemplo). */

export interface PuertaVista {
  valor: number;
  min: number;
  max: number;
  onCambio: (grados: number) => void;
  /** Abre o cierra animando hasta ese valor. */
  onAnimar: (destino: number) => void;
}

interface Props {
  panel: PanelTableroOut;
  conductor: string | null;
  onConductor: (id: string | null) => void;
  onEncuadrar: (piezas: readonly string[]) => void;
  puerta?: PuertaVista;
}

export default function VistaTablero({ panel, conductor, onConductor, onEncuadrar, puerta }: Props) {
  const [elegido, setElegido] = useState<ItemTablero | null>(null);
  const [abierto, setAbierto] = useState(false);
  const filtro = elegido && elegido.conductores.length > 1 ? elegido.conductores : null;
  const acciones: AccionesTablero = {
    encuadrar: onEncuadrar,
    dibujar: onConductor,
    elegir: (it) => {
      setElegido(it);
      if (it.conductores.length > 1) setAbierto(true); // sus conductores se listan en el detalle
    },
  };
  const v = panel.veredicto;
  const boton = puerta ? accionPuerta(puerta.valor, puerta.max) : null;
  return (
    <div className="tablero">
      <Veredicto severidad={v.severidad} frase={v.frase} nota={v.nota} />
      <ItemsAtencion items={itemsDeAtencion(panel.items, acciones)} rotulo="Lo que pide atención en el tablero" />
      {elegido?.detalle && <p className="tb-explica" aria-live="polite">{elegido.detalle}</p>}
      {elegido?.tecnico && (
        <VerDetalle resumen="Detalle técnico">
          <p>{elegido.tecnico}</p>
        </VerDetalle>
      )}
      {puerta && boton && (
        <div className="tb-puerta">
          <Deslizador rotulo="Puerta" valor={Math.round(puerta.valor)} min={puerta.min} max={puerta.max} unidad="°"
            onCambio={puerta.onCambio} />
          <button type="button" className="tb-boton" onClick={() => puerta.onAnimar(boton.destino)}>
            {boton.rotulo}
          </button>
        </div>
      )}
      {panel.detalle && (
        <details className="tb-plegable" open={abierto} onToggle={(e) => setAbierto(e.currentTarget.open)}>
          <summary>Detalle</summary>
          {abierto && (
            <DetalleTablero panel={panel} acciones={acciones} conductor={conductor} filtro={filtro}
              quitarFiltro={() => setElegido(null)} />
          )}
        </details>
      )}
    </div>
  );
}
