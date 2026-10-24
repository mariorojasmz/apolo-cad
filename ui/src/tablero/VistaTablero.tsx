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
   (un veredicto), debajo sólo lo que pide atención (clic → la cámara vuela y lo muestra, y la
   fila elegida abre su frase debajo), la puerta con su deslizador y, a pedido, el detalle. Recibe
   todo por props: la monta el panel real (`PanelTablero.tsx`, con la API y el visor) y el
   muestrario (datos de ejemplo). Un tablero que no se pudo armar sólo dice eso y el motivo. */

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
  onEncuadrar: (piezas: readonly string[], puntos?: readonly (readonly number[])[]) => void;
  puerta?: PuertaVista;
  /** Para el muestrario (capturas de la revisión a ciegas): el detalle abierto y un ítem elegido. */
  inicial?: { detalle?: boolean; item?: string };
}

export default function VistaTablero({ panel, conductor, onConductor, onEncuadrar, puerta, inicial }: Props) {
  const [elegido, setElegido] = useState<ItemTablero | null>(
    () => panel.items.find((it) => it.clave === inicial?.item) ?? null);
  const [abierto, setAbierto] = useState(!!inicial?.detalle);
  const v = panel.veredicto;
  if (!panel.armado) {
    const tecnico = panel.items.find((it) => it.tecnico)?.tecnico;
    return (
      <div className="tablero">
        <Veredicto severidad={v.severidad} frase={v.frase} nota={v.nota} />
        {tecnico && <VerDetalle resumen="Detalle técnico"><p>{tecnico}</p></VerDetalle>}
      </div>
    );
  }
  const filtro = elegido && elegido.conductores.length > 1 ? elegido.conductores : null;
  const acciones: AccionesTablero = {
    encuadrar: onEncuadrar,
    dibujar: onConductor,
    elegir: (it) => {
      setElegido(it);
      if (it.conductores.length > 1) setAbierto(true); // sus conductores se listan en el detalle
    },
  };
  const boton = puerta ? accionPuerta(puerta.valor, puerta.max) : null;
  return (
    <div className="tablero">
      <Veredicto severidad={v.severidad} frase={v.frase} nota={v.nota} />
      <ItemsAtencion items={itemsDeAtencion(panel.items, acciones, panel)} rotulo="Lo que pide atención en el tablero"
        elegida={elegido?.clave} debajo={elegido?.detalle ? <p aria-live="polite">{elegido.detalle}</p> : null} />
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
