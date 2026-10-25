import { ChevronRight } from "lucide-react";
import { useVivo } from "../vivo/estado";
import type { ValvulaVivo } from "../vivo/protocolo";
import { enviar } from "../vivo/sesion";
import { alternarManual, ponerPuestos, puestosDe, useManual } from "./manual";
import "./neumatica.css";

/* «Accionamiento manual» en el panel «Mandos» (plan V8.9 D12): el botón de la propia válvula, que
   prueba el cilindro sin el PLC. No es un mando del operador: va en un grupo PLEGADO, al final.
   Es ENCLAVADO, como el real (`cosim/modelos/electrovalvula.py`): queda accionado hasta soltarlo.
   La posición de la válvula se lee de su señal (`<des>.posicion`). */

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
  const sesion = useVivo((s) => s.inicio);
  const clave = useManual((st) => puestosDe(st, sesion, v.designacion).join(",")); // primitivo
  const enclavados = clave ? clave.split(",") : [];
  const alternar = (lado: string) => {
    const { quedan, acciones } = alternarManual(v.designacion, enclavados, lado);
    for (const a of acciones) enviar(a);
    ponerPuestos(sesion, v.designacion, quedan);
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
