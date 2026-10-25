import { useVivo } from "../vivo/estado";
import { historia } from "../vivo/medicion";
import { aireMedio, senalesDeAire, textoAire, VENTANA_S } from "./aire";
import "./neumatica.css";

/* «Aire: 14 NL/min» en la barra de la sesión viva (plan V8.9 D12): la media móvil del caudal de
   los FRL (`aire.ts`). Se recalcula con cada publicación de la sesión (≤ 10 Hz); sin FRL, nada. */

export default function AireVivo() {
  useVivo((s) => s.t); // primitivo: se re-dibuja al ritmo de la sesión
  const senales = senalesDeAire(Object.keys(useVivo.getState().lecturas));
  if (!senales.length) return null;
  const nl = aireMedio(historia, senales);
  if (nl === undefined) return null;
  return (
    <span className="bv-aire" aria-label={`Aire: ${textoAire(nl)}, media de los últimos ${VENTANA_S} segundos`}>
      <span>Aire: </span>{textoAire(nl)}
    </span>
  );
}
