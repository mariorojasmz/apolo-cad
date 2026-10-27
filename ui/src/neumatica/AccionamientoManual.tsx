import { ChevronRight } from "lucide-react";
import { nombrePrincipal } from "../diseno/nombres";
import { useVivo } from "../vivo/estado";
import { CabezaAparato } from "../vivo/FilaMando";
import type { ValvulaVivo } from "../vivo/protocolo";
import { enviar } from "../vivo/sesion";
import { alternarManual, ladosManual, nombrePosicion, rotuloLado } from "./manual";
import "./neumatica.css";

/* «Accionamiento manual» en el panel «Mandos» (plan V8.9 D12): el botón de la propia válvula, que
   prueba el cilindro sin el PLC. No es un mando del operador: va en un grupo PLEGADO, al final.
   Es ENCLAVADO, como el real (`cosim/modelos/electrovalvula.py`): queda accionado hasta soltarlo.
   Lo enclavado y la posición se LEEN de sus señales (`<des>.manual`, `<des>.posicion`): lo que
   ponga el agente u otra pestaña se ve igual aquí. La fila es la de «Mandos» (plan
   nombres-por-funcion D9): la válvula por lo que hace, y al lado, la posición por su nombre
   («Compuerta cerrada»), nunca «posición 14». */

/** `abierto`: el grupo arranca desplegado (el muestrario, para su captura). */
export default function AccionamientoManual({ quieto, abierto }: { quieto: boolean; abierto?: boolean }) {
  const valvulas = useVivo((s) => s.inicio?.valvulas);
  const conManual = (valvulas ?? []).filter((v) => v.manual);
  if (!conManual.length) return null;
  return (
    <details className="nm-manual" open={abierto || undefined}>
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
  const nombre = nombrePrincipal(v);
  const donde = nombrePosicion(posicion, v.lados, v.estados);
  return (
    <li className="fila-mando">
      <CabezaAparato a={v} />
      <div className="fila-mando-accion">
        {donde && <span className="estado-mando" aria-live="polite">{donde}</span>}
        <div className="fila-mando-control" role="group" aria-label={`Accionamiento manual: ${nombre}`}>
          {v.lados.map((lado) => {
            const puesto = enclavados.includes(lado);
            const rotulo = rotuloLado(lado, puesto, uno, v.estados);
            return (
              <button key={lado} type="button" disabled={quieto} aria-pressed={puesto} className={`boton-mando${puesto ? " apretado" : ""}`}
                aria-label={`${rotulo}: ${nombre}`} onClick={() => alternar(lado)}>
                {rotulo}
              </button>
            );
          })}
        </div>
      </div>
    </li>
  );
}
