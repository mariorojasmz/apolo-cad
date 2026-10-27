import { createContext, memo, useContext, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import Ayuda from "../ui/Ayuda";
import { abreYCierra, estadoDeMando, estadoDesdeValor, senalDeEstado, valorVisto } from "./accionar";
import { useVivo } from "./estado";
import { alApretar, alSoltar, colorFisico, encendido, esMomentaneo, girar, llevarA, rotuloAccion, type Accion } from "./mandos";
import NombreDeAparato from "../diseno/NombreAparato";
import {
  estadoJuntoAlBoton, muestraColorFisico, nombrePrincipal, segmentoLeido, segmentosDe, type Leidas, type PasoSiguiente,
} from "./nombresMandos";
import type { MandoVivo, NombreAparato, PilotoVivo } from "./protocolo";
import { accionar as accionarPorWs } from "./sesion";
import Segmentado from "./Segmentado";
import "./mandos.css";

/* La fila de un mando, de un piloto o de una lectura en «Mandos» (plan nombres-por-funcion D9,
   D10, D16): lo que HACE manda (`--fw-medio`) y la designación va detrás, chica y en tinta
   secundaria; la `descripcion`, sólo en la ⓘ. Un mando que se queda es un control segmentado con
   el estado LEÍDO de su señal; el pulsador y la seta, un botón con verbo; el rearme dice al lado
   cómo están los relés que rearma. Nada se deshabilita por no tener efecto ahora. El control del
   paso que pide el veredicto (`paso`) va con el estilo primario del tema; ningún otro (F5b). El
   cuadrado del color físico, sólo donde el color informa (`muestraColorFisico`). */

/** Cómo se manda la acción de un mando: por el WebSocket; el muestrario la simula. */
export const AccionarMando = createContext<(a: Accion, m: MandoVivo) => void>(accionarPorWs);

/** Lo leído de la sesión, para las funciones puras de `nombresMandos.ts`. */
export const leidasDe = (s: { lecturas: Record<string, number>; textos: Record<string, string> }): Leidas => ({
  valor: (senal) => s.lecturas[senal],
  texto: (senal) => s.textos[senal],
});

/** El nombre de la fila: el rótulo, la designación detrás y la ⓘ con la descripción. */
export function CabezaAparato({ a }: { a: NombreAparato & { designacion: string } }) {
  return (
    <div className="cabeza-aparato">
      {/* la ⓘ va pegada a la designación: nunca sola en su línea (F5b) */}
      <NombreDeAparato a={a} cola={a.descripcion && <Ayuda tema={nombrePrincipal(a)}>{a.descripcion}</Ayuda>} />
    </div>
  );
}

/** El color físico como variables CSS de la tapa (y el fondo amarillo de la seta). */
function tapa(color: string | null, fondo?: string): CSSProperties {
  return {
    "--tapa": colorFisico(color) ?? "var(--panel3)",
    "--fondo-tapa": colorFisico(fondo) ?? "transparent",
  } as CSSProperties;
}

/** La fila de un mando. `paso`: el control de la acción que pide el veredicto, si es de este mando.
 *  Memorizada: la lista se re-dibuja con cada lectura (el veredicto) y la fila sólo con lo suyo. */
export const FilaMando = memo(function FilaMando({ m, quieto, paso }: { m: MandoVivo; quieto: boolean; paso?: PasoSiguiente }) {
  const accionar = useContext(AccionarMando);
  // selectores PRIMITIVOS: un objeto nuevo por lectura re-renderizaría sin fin
  const senal = senalDeEstado(m);
  const v = useVivo((s) => (senal ? valorVisto(s, senal) : undefined));
  const leido = useVivo((s) => segmentoLeido(m, leidasDe(s)));
  const junto = useVivo((s) => estadoJuntoAlBoton(m, leidasDe(s)));
  const estado = estadoDesdeValor(m, v);
  const accionado = v !== undefined && v >= 0.5 && !abreYCierra(m);
  const segmentos = segmentosDe(m);
  const nombre = nombrePrincipal(m);
  return (
    <li className="fila-mando">
      {muestraColorFisico(m) && (
        <span className={`tapa-mando tapa-${m.tipo}${accionado ? " accionada" : ""}`} style={tapa(m.color, m.fondo)} aria-hidden />
      )}
      <CabezaAparato a={m} />
      {/* el estado y el control van juntos: en angosto bajan juntos, nunca el botón solo */}
      <div className="fila-mando-accion">
        {junto && <span className="estado-mando" aria-live="polite">{junto}</span>}
        <div className="fila-mando-control">
          {segmentos ? (
            <Segmentado etiqueta={nombre} segmentos={segmentos} valor={leido} quieto={quieto} primario={paso?.clave}
              alElegir={(clave) => accionar(llevarA(m, clave), m)} />
          ) : m.tipo === "pulsador" ? (
            <>
              {(m.actuadores?.length ?? 0) > 1
                ? m.actuadores!.map((a) => <BotonMando key={a} m={m} actuador={a} rotulo={m.estados?.[a] || a} quieto={quieto} />)
                : <BotonMando m={m} rotulo={rotuloAccion(m, estado)} quieto={quieto} activo={accionado}
                  primario={!!paso && !paso.clave} />}
              {m.potenciometro && <Potenciometro m={m} quieto={quieto} />}
            </>
          ) : (
            <BotonMando m={m} rotulo={rotuloAccion(m, estado)} quieto={quieto} primario={!!paso && !paso.clave}
              activo={m.tipo === "seta" ? estado.retenida : abreYCierra(m) ? estado.cerrado === false : undefined} />
          )}
        </div>
      </div>
    </li>
  );
});

/** Un botón que se comporta como el mando: el pulsador con resorte vuelve al soltar. `primario`:
 *  es el paso que pide el veredicto. */
function BotonMando({ m, rotulo, actuador, quieto, activo, primario }: {
  m: MandoVivo; rotulo: string; actuador?: string; quieto: boolean; activo?: boolean; primario?: boolean;
}) {
  const accionar = useContext(AccionarMando);
  const [abajo, setAbajo] = useState(false);
  const abajoRef = useRef(false); // el soltar puede llegar dos veces antes del re-render
  const apretar = () => {
    const a = alApretar(m, { ...estadoDeMando(m, useVivo.getState()), actuador });
    if (a) accionar(a, m);
    abajoRef.current = true;
    setAbajo(true);
  };
  const soltar = () => {
    if (!abajoRef.current) return;
    abajoRef.current = false;
    setAbajo(false);
    const a = alSoltar(m, { actuador });
    if (a) accionar(a, m);
  };
  const tecla = (e: KeyboardEvent, bajar: boolean) => {
    if (e.key !== " " && e.key !== "Enter") return;
    e.preventDefault();
    if (bajar && !e.repeat && !abajoRef.current) apretar();
    if (!bajar) soltar();
  };
  return (
    <button
      type="button"
      className={`boton-mando${abajo || activo ? " apretado" : ""}${primario ? " primary" : ""}`}
      disabled={quieto}
      aria-pressed={activo ?? abajo}
      aria-label={`${rotulo}: ${nombrePrincipal(m)}`}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        try {
          e.currentTarget.setPointerCapture(e.pointerId); // soltar fuera del botón también suelta
        } catch {
          /* puntero sin captura (sintético): basta el pointerup */
        }
        apretar();
      }}
      onPointerUp={soltar}
      onPointerCancel={soltar}
      onLostPointerCapture={esMomentaneo(m) ? soltar : undefined}
      onKeyDown={(e) => tecla(e, true)}
      onKeyUp={(e) => tecla(e, false)}
    >
      {rotulo}
    </button>
  );
}

function Potenciometro({ m, quieto }: { m: MandoVivo; quieto: boolean }) {
  const accionar = useContext(AccionarMando);
  const valor = useVivo((s) => s.lecturas[`${m.designacion}.potenciometro`]);
  return (
    <input type="range" min={0} max={1} step={0.01} disabled={quieto} value={valor ?? 0}
      aria-label={`Potenciómetro: ${nombrePrincipal(m)}`}
      onChange={(e) => accionar(girar(m, Number(e.target.value)), m)} />
  );
}

export function FilaPiloto({ p }: { p: PilotoVivo }) {
  const on = useVivo((s) => encendido(s.lecturas[p.senal]));
  return (
    <li className="fila-mando">
      <span className={`lampara${on ? " encendida" : ""}`} style={tapa(p.color)} aria-hidden />
      <CabezaAparato a={p} />
      <span className="estado-mando">{on ? "Encendido" : "Apagado"}</span>
    </li>
  );
}
