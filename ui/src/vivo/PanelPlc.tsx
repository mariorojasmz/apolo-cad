import { useMemo } from "react";
import { useStore } from "../state/store";
import { abrirPanel } from "./abrirPanel";
import { useVivo } from "./estado";
import { indiceSenales, lineasDelPrograma, programasDelDocumento, valorSt, type FuentePlc } from "./programa";
import "./vivo.css";

/* Panel «PLC» de la máquina viva (plan V8.4 D8): el texto ST de cada programa con el valor
   actual de cada variable al lado, como el monitor online de un PLC, y el modo del PLC
   (RUN/STOP) con su falla. Sin sesión viva se lee el programa, sin valores. */

export default function PanelPlc() {
  const commands = useStore((s) => s.scene?.document.commands);
  const programas = useMemo(() => programasDelDocumento(commands ?? []), [commands]);
  const fase = useVivo((s) => s.fase);
  const viva = fase === "corriendo" || fase === "pausa" || fase === "fin";
  if (!programas.length) {
    return (
      <section className="history panel-mandos">
        <p className="hint">Aquí vas a ver el programa del PLC con sus valores en vivo. Este tablero no tiene programa: pídele al agente que lo escriba.</p>
      </section>
    );
  }
  return (
    <section className="history panel-mandos panel-plc">
      {!viva && (
        <div className="kin-actions">
          <span className="hint">Abre la sesión viva para ver los valores.</span>
          <button onClick={() => void abrirPanel("mandos")}>Abrir la sesión viva</button>
        </div>
      )}
      {programas.map((p) => <Programa key={p.comando} p={p} viva={viva} />)}
    </section>
  );
}

function EstadoPlc({ plc }: { plc: string }) {
  const estado = useVivo((s) => s.textos[`${plc}.estado`]);
  const falla = useVivo((s) => s.textos[`${plc}.falla`]);
  if (!estado && !falla) return null;
  return (
    <>
      {estado && <span className={`modo-plc${estado.toUpperCase() === "RUN" ? " en-run" : ""}`}>{estado.toUpperCase()}</span>}
      {falla && <span className="estado-aviso falla-plc">Falla: {falla}</span>}
    </>
  );
}

function Programa({ p, viva }: { p: FuentePlc; viva: boolean }) {
  const inicio = useVivo((s) => s.inicio);
  const lecturas = useVivo((s) => s.lecturas);
  const n = Object.keys(lecturas).length;
  const lineas = useMemo(() => {
    const nombres = indiceSenales([...(inicio?.senales ?? []), ...Object.keys(useVivo.getState().lecturas)]);
    return lineasDelPrograma(p.fuente, p.plc, nombres);
  }, [p.fuente, p.plc, inicio, n]); // `n`: aparecen señales nuevas
  return (
    <div className="programa-plc">
      <header>
        <h3>{p.plc}</h3>
        {p.ciclo_ms !== undefined && <span className="hint">ciclo de {p.ciclo_ms} ms</span>}
        {viva && <EstadoPlc plc={p.plc} />}
      </header>
      <pre className="codigo-st" aria-label={`Programa de ${p.plc}`}>
        {lineas.map((ln, i) => (
          <div key={i} className="linea-st">
            {ln.length === 0 ? " " : ln.map((f, j) => {
              if (f.tipo === "comentario") return <span key={j} className="st-comentario">{f.texto}</span>;
              if (f.tipo === "codigo") return <span key={j}>{f.texto}</span>;
              const v = viva && f.senal ? lecturas[f.senal] : undefined;
              return (
                <span key={j} className="st-variable">
                  {f.texto}
                  {viva && f.senal && (
                    <span className={`st-valor${f.variable.tipo === "BOOL" && v !== undefined && v >= 0.5 ? " verdadero" : ""}`}>
                      {valorSt(v, f.variable.tipo)}
                    </span>
                  )}
                </span>
              );
            })}
          </div>
        ))}
      </pre>
    </div>
  );
}
