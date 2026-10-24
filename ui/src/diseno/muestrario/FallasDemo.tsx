import { useState } from "react";
import { Pause, Square, X } from "lucide-react";
import { segundos } from "../../viewport/marcha/serie";
import { rotuloFase, textoFactor } from "../../vivo/barra";
import FallasActivas from "../../vivo/FallasActivas";
import FallasVivas from "../../vivo/FallasVivas";
import { prepararSesionDemo, simularLocal } from "./datosVivo";
import "../../viewport/marcha/marcha.css";

/* «Simular falla» y las fallas activas de la barra (plan cosim-fallas D7) en el muestrario, con
   una sesión viva de ejemplo (`datosVivo.ts`): simular y quitar cambian la barra como lo haría
   el servidor. `?fallas=0|1|3` (por defecto 1) y `?lista=1` (la lista de la barra abierta). */

const q = () => new URLSearchParams(window.location.search);

/** Prepara la store de la sesión viva una sola vez, antes del primer render. */
function useSesionDemo(): void {
  useState(() => {
    const n = Number(q().get("fallas") ?? 1);
    prepararSesionDemo(Number.isFinite(n) ? Math.max(0, Math.min(3, n)) : 1);
    return true;
  });
}

export function PanelFallasDemo() {
  useSesionDemo();
  return (
    <div className="panel-mandos">
      <FallasVivas quieto={false} alSimular={simularLocal} />
    </div>
  );
}

export function BarraFallasDemo() {
  useSesionDemo();
  const f = textoFactor(1);
  return (
    <div className="mu-barra">
      <div className="barra-marcha barra-vivo" role="toolbar" aria-label="Máquina viva de ejemplo">
        <FallasActivas alQuitar={simularLocal} listaAbierta={q().get("lista") === "1"} />
        <span className="bv-fase bv-corriendo">{rotuloFase("corriendo")}</span>
        <span className="bm-tiempo">{segundos(12.4)}</span>
        <span className="bv-factor">{f.texto}</span>
        <span className="bv-espacio" />
        <span className="bv-paneles" role="group" aria-label="Paneles de la máquina viva">
          <button type="button" aria-pressed="true">Mandos</button>
          <button type="button">Señales</button>
          <button type="button">PLC</button>
        </span>
        <button type="button" aria-label="Pausar" title="Pausar"><Pause size={15} /></button>
        <button type="button" aria-label="Parar la sesión" title="Parar la sesión"><Square size={14} /></button>
        <button type="button" aria-label="Cerrar la máquina viva" title="Cerrar la máquina viva"><X size={15} /></button>
      </div>
    </div>
  );
}
