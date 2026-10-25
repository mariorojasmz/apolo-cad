import { ChevronRight } from "lucide-react";
import { useVivo } from "../vivo/estado";
import type { ValvulaVivo } from "../vivo/protocolo";
import { enviar } from "../vivo/sesion";
import { alternarManual, ladosManual, posicionPersona } from "./manual";
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
    <details className="nm-manual">
      <summary>
        <ChevronRight className="nm-plegado" size={14} aria-hidden="true" />
        <h3>Accionamiento manual</h3>
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
  const uno = v.lados.length === 1;
  return (
    <li className="fila-mando">
      <div className="fila-mando-nombre">
        <strong>{v.designacion}</strong>
        <span className="hint">
          {enclavados.length ? "Activado a mano" : "Sin accionar"} · posición {posicionPersona(posicion, v.lados)}
        </span>
      </div>
      <div className="fila-mando-control" role="group" aria-label={`Accionamiento manual de ${v.designacion}`}>
        {v.lados.map((lado) => {
          const puesto = enclavados.includes(lado);
          const verbo = puesto ? "Soltar" : "Accionar a mano";
          return (
            <button key={lado} type="button" disabled={quieto} aria-pressed={puesto} className={`boton-mando${puesto ? " apretado" : ""}`}
              aria-label={`${verbo} el lado ${lado} de ${v.designacion}`} onClick={() => alternar(lado)}>
              {uno ? verbo : `${verbo} · ${lado}`}
            </button>
          );
        })}
      </div>
    </li>
  );
}
