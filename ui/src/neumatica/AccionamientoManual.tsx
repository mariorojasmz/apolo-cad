import { ChevronRight } from "lucide-react";
import { useVivo } from "../vivo/estado";
import type { ValvulaVivo } from "../vivo/protocolo";
import { enviar } from "../vivo/sesion";
import { alternarManual, ladosManual } from "./manual";
import "./neumatica.css";

/* «Accionamiento manual» en el panel «Mandos» (plan V8.9 D12): el botón de la propia válvula, que
   prueba el cilindro sin el PLC. No es un mando del operador: va en un grupo PLEGADO, al final.
   Es ENCLAVADO, como el real (`cosim/modelos/electrovalvula.py`): queda accionado hasta soltarlo.
   Lo enclavado y la posición se LEEN de sus señales (`<des>.manual`, `<des>.posicion`): lo que
   ponga el agente u otra pestaña se ve igual aquí. */

export default function AccionamientoManual({ quieto }: { quieto: boolean }) {
  const valvulas = useVivo((s) => s.inicio?.valvulas);
  const conManual = (valvulas ?? []).filter((v) => v.manual);
  if (!conManual.length) return null;
  return (
    <details className="rama-senales nm-manual">
      <summary>
        <ChevronRight className="nm-plegado" size={14} aria-hidden="true" />
        <strong>Accionamiento manual</strong>
        <span className="hint cuenta-senales">{conManual.length}</span>
      </summary>
      <ul className="lista-mandos">
        {conManual.map((v) => <FilaValvula key={v.designacion} v={v} quieto={quieto} />)}
      </ul>
    </details>
  );
}

function FilaValvula({ v, quieto }: { v: ValvulaVivo; quieto: boolean }) {
  const posicion = useVivo((s) => s.textos[`${v.designacion}.posicion`]);
  const manual = useVivo((s) => s.textos[`${v.designacion}.manual`]);
  const enclavados = ladosManual(manual);
  const alternar = (lado: string) => {
    for (const a of alternarManual(v.designacion, enclavados, lado)) enviar(a);
  };
  return (
    <li className="fila-mando">
      <div className="fila-mando-nombre">
        <strong>{v.designacion}</strong>
        <span className="hint">{posicion ? `Electroválvula en ${posicion}` : "Electroválvula"}</span>
      </div>
      <div className="fila-mando-control selector-mando" role="group" aria-label={`Accionamiento manual de ${v.designacion}`}>
        {v.lados.map((lado) => {
          const puesto = enclavados.includes(lado);
          return (
            <button key={lado} type="button" disabled={quieto} aria-pressed={puesto} className={puesto ? "apretado" : ""}
              aria-label={`${puesto ? "Soltar" : "Accionar"} a mano el lado ${lado} de ${v.designacion}`}
              onClick={() => alternar(lado)}>
              {lado}
            </button>
          );
        })}
      </div>
    </li>
  );
}
