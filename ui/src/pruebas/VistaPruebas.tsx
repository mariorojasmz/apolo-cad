import { useEffect, useState } from "react";
import { ChevronRight, MapPin } from "lucide-react";
import EstadoVacio from "../diseno/EstadoVacio";
import IconoSeveridad from "../diseno/IconoSeveridad";
import Veredicto from "../diseno/Veredicto";
import { ROTULO_SEVERIDAD } from "../diseno/atencion";
import { fechaCorta, progresoCorrida, textoIncidencia, type Corrida } from "./vista";
import type { DetallePrueba, FilaPrueba, Incidencia, PanelPruebasOut } from "./tipos";
import "./pruebas.css";

/* La vista del panel «Pruebas» (plan visor-para-evaluar D1–D5): arriba, «¿pasan las pruebas de
   mi máquina?» («15 de 16 pasan · 1 vencido»); debajo, cada escenario con su semáforo, la fecha
   y el balance de producto. Al abrir uno, lo que falló con su cifra y el producto trabado o
   perdido con su lugar y su hora (clic → la cámara va al lugar), y «Correr» / «Verla en vivo».
   Todo por props: la monta el panel (`PanelPruebas.tsx`) y el muestrario. */

export interface AccionesPruebas {
  alternar: (nombre: string) => void;
  correr: (fila: FilaPrueba) => void;
  enVivo: (nombre: string) => void;
  verLugar: (i: Incidencia) => void;
}

interface Props {
  panel: PanelPruebasOut;
  abierto: string | null;
  detalle: DetallePrueba | null;
  corridas: Record<string, Corrida>;
  fallos: Record<string, string>;
  acciones: AccionesPruebas;
  /** El reloj (ms) del progreso: el muestrario lo fija para sus capturas. */
  ahora?: number;
}

/** El reloj del progreso: un tic por segundo mientras algo corre. */
function useReloj(activo: boolean, fijo?: number): number {
  const [t, setT] = useState(() => fijo ?? Date.now());
  useEffect(() => {
    if (!activo || fijo !== undefined) return;
    const id = window.setInterval(() => setT(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [activo, fijo]);
  return fijo ?? t;
}

export default function VistaPruebas({ panel, abierto, detalle, corridas, fallos, acciones, ahora }: Props) {
  const reloj = useReloj(Object.keys(corridas).length > 0, ahora);
  if (!panel.escenarios.length || !panel.veredicto) {
    return (
      <EstadoVacio titulo="Aquí vas a ver si la máquina pasa sus pruebas">
        Cada prueba es un escenario de la simulación con lo que tiene que cumplir. Pídele al agente que declare uno.
      </EstadoVacio>
    );
  }
  return (
    <div className="pruebas">
      <Veredicto severidad={panel.veredicto.severidad} frase={panel.veredicto.frase} />
      <ul className="pr-lista" aria-label="Pruebas de la máquina">
        {panel.escenarios.map((f) => (
          <li key={f.nombre}>
            <button type="button" className={`pr-fila${abierto === f.nombre ? " elegida" : ""}`}
              aria-expanded={abierto === f.nombre} onClick={() => acciones.alternar(f.nombre)}
              aria-label={`${f.nombre}: ${ROTULO_SEVERIDAD[f.severidad]}, ${f.rotulo}`}>
              <IconoSeveridad severidad={f.severidad} tamano={15} />
              <span className="pr-nombre">{f.nombre}</span>
              <span className="pr-estado">{f.rotulo}</span>
              <ChevronRight className="pr-ir" size={14} aria-hidden="true" />
              <span className="pr-bajo">
                {[fechaCorta(f.fecha, new Date(reloj)), f.balance].filter(Boolean).join(" · ") || "Todavía no se corrió"}
              </span>
            </button>
            {corridas[f.nombre] && <Progreso c={corridas[f.nombre]} ahora={reloj} />}
            {abierto === f.nombre && (
              <Detalle fila={f} detalle={detalle} corriendo={!!corridas[f.nombre]} fallo={fallos[f.nombre]}
                acciones={acciones} />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Progreso({ c, ahora }: { c: Corrida; ahora: number }) {
  const { frase, fraccion } = progresoCorrida(c, ahora);
  return (
    <div className="pr-progreso" role="status">
      <span className="pr-barra" aria-hidden="true">
        <span className={fraccion === null ? "pr-relleno indeterminado" : "pr-relleno"}
          style={fraccion === null ? undefined : { transform: `scaleX(${fraccion})` }} />
      </span>
      <span className="pr-nota">{frase}</span>
    </div>
  );
}

function Detalle({ fila, detalle, corriendo, fallo, acciones }: {
  fila: FilaPrueba; detalle: DetallePrueba | null; corriendo: boolean; fallo?: string; acciones: AccionesPruebas;
}) {
  return (
    <div className="pr-detalle">
      {fila.descripcion && <p className="pr-texto">{fila.descripcion}</p>}
      {fila.motivo && (
        <p className="pr-texto">Ya no vale: {fila.motivo}.{fila.ultimo ? ` La última vez: ${fila.ultimo.toLowerCase()}.` : ""}</p>
      )}
      {fallo && <p className="estado-aviso">{fallo}</p>}
      {!detalle ? (
        <p className="pr-nota">Leyendo la prueba…</p>
      ) : (
        <>
          {detalle.fallidas.length > 0 && (
            <section className="pr-seccion">
              <h4 className="pr-titulo">Lo que no cumplió</h4>
              <ul className="pr-filas">
                {detalle.fallidas.map((a) => (
                  <li key={a.asercion} className="pr-item pr-fallida">
                    <span className="pr-asercion">{a.asercion}</span>
                    <span className="pr-cifra">{a.cifra}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {detalle.incidencias.length > 0 && (
            <section className="pr-seccion">
              <h4 className="pr-titulo">El producto</h4>
              <ul className="pr-filas">
                {detalle.incidencias.map((i, k) => (
                  <li key={k}>
                    {i.pieza || i.punto_mm ? (
                      <button type="button" className="pr-item pr-lugar" onClick={() => acciones.verLugar(i)}>
                        <span>{textoIncidencia(i)}</span>
                        <MapPin size={14} className="pr-ir" aria-hidden="true" />
                      </button>
                    ) : (
                      <span className="pr-item">{textoIncidencia(i)}</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {detalle.fallidas.length === 0 && detalle.incidencias.length === 0 && fila.fecha && (
            <p className="pr-nota">
              {detalle.n_aserciones === 1 ? "Cumplió su condición." : `Cumplió sus ${detalle.n_aserciones} condiciones.`}
            </p>
          )}
        </>
      )}
      <div className="pr-acciones">
        <button type="button" className="primary" disabled={corriendo} onClick={() => acciones.correr(fila)}>
          {corriendo ? "Corriendo…" : "Correr"}
        </button>
        <button type="button" onClick={() => acciones.enVivo(fila.nombre)}>Verla en vivo</button>
      </div>
    </div>
  );
}
