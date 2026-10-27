import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import NombreAparato from "../diseno/NombreAparato";
import { nombreEnLinea } from "../diseno/nombres";
import {
  altoTexto, colorPresion, conNombre, convieneAmpliar, detalleSimbolo, escalaEsquema, posicionDe, presionDe, vistaConTextos,
  RAMPA_PRESION, SIN_PRESION, topeLeyenda, type Lector,
} from "./esquema";
import type { EsquemaNeumatico, NombreNeumatico, SimboloEsquema } from "./tipos";

/* El esquema ISO 1219 del circuito de aire, EN LÍNEA (plan V8.9 D12): la lámina de la F5 en
   primitivas, con la tinta del tema. Cada símbolo es un botón (clic → el aparato se elige y la
   cámara vuela a su pieza); un aparato elegido en el 3D se marca aquí y debajo se lee qué es (los
   rótulos de 2 mm de la lámina no van en el SVG: ilegibles en un panel). Las designaciones tienen
   un piso de tamaño (`altoTexto`). Con `lector` (la sesión viva) cada línea se tiñe por su presión,
   con su escala, y la caja de la posición en que está cada válvula se marca con un fondo y un
   trazo NEUTROS (el azul es de la presión; el acento, de lo elegido): se ve conmutar. */

interface Props {
  esquema: EsquemaNeumatico;
  /** Las señales de la sesión viva; null sin sesión (el esquema en tinta, en reposo). */
  lector: Lector | null;
  elegidos: ReadonlySet<string>;
  onElegir: (s: SimboloEsquema) => void;
  /** El rótulo de la sección («Esquema», «Esquema en vivo»), en la fila de «Ampliar». */
  titulo: string;
  /** Lo que hace cada aparato, por designación (del servidor): nombra al elegido. */
  nombres?: Record<string, NombreNeumatico>;
}

/** Grosor de los trazos (mm de la lámina): la tinta y la línea teñida, más gruesa para que el
   color se lea. */
const TINTA_MM = 0.35;
const LINEA_VIVA_MM = 0.7;
const HOLGURA_MM = 1.5;

export default function EsquemaNeumatica({ esquema: e, lector, elegidos, onElegir, titulo, nombres }: Props) {
  const caja = useRef<HTMLDivElement>(null);
  const [ancho, setAncho] = useState(0);
  useEffect(() => {
    const el = caja.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setAncho(el.clientWidth));
    ro.observe(el);
    setAncho(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  const [ampliado, setAmpliado] = useState(false);
  // la vista con lugar para los textos agrandados: ninguno se corta en el borde (F5b)
  const [vx, vy, vw, vh] = vistaConTextos(e.vista, e.textos, ancho, ampliado);
  const k = escalaEsquema(ancho, vw, ampliado);
  const activas: [string, number[]][] = lector ? e.valvulas.flatMap((v) => {
    const pos = posicionDe(v, lector);
    const c = pos !== undefined ? v.cajas[pos] : undefined;
    return c ? [[v.designacion, c] as [string, number[]]] : [];
  }) : [];
  const elegidosSim = e.simbolos.filter((s) => elegidos.has(s.designacion));
  const tecla = (ev: KeyboardEvent, s: SimboloEsquema) => {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    ev.preventDefault();
    onElegir(s);
  };
  return (
    <>
      <div className="nm-cabecera">
        <h3 className="tb-titulo">{titulo}</h3>
        {(ampliado || convieneAmpliar(ancho, vw)) && (
          <button type="button" className="tb-enlace nm-ampliar" aria-pressed={ampliado} onClick={() => setAmpliado(!ampliado)}>
            {ampliado ? "Ajustar al ancho" : "Ampliar"}
          </button>
        )}
      </div>
      <div className="nm-esquema" ref={caja}>
        <svg viewBox={`${vx} ${vy} ${vw} ${vh}`} width={vw * k} height={vh * k} role="group"
          aria-label="Esquema neumático ISO 1219" className={lector ? "vivo" : undefined}>
          {activas.length > 0 && (
            <g className="nm-posiciones-fondo">
              {activas.map(([d, c]) => <rect key={d} x={c[0]} y={c[1]} width={c[2]} height={c[3]} />)}
            </g>
          )}
          <g className="nm-tinta" strokeWidth={TINTA_MM} strokeLinecap="round" fill="none">
            {e.trazos.map(([x1, y1, x2, y2, t], i) => (
              <line key={`t${i}`} x1={x1} y1={y1} x2={x2} y2={y2} strokeDasharray={t ? "2.4 0.9" : undefined} />
            ))}
            {e.circulos.map(([x, y, r, lleno], i) => (
              <circle key={`c${i}`} cx={x} cy={y} r={r} className={lleno ? "lleno" : undefined} />
            ))}
            {e.poligonos.map((p, i) => (
              <polygon key={`p${i}`} points={p.puntos.map((q) => q.join(",")).join(" ")}
                className={p.lleno ? "lleno" : undefined} strokeLinejoin="round" />
            ))}
          </g>
          <g className="nm-lineas" strokeLinecap="round">
            {e.lineas.map((ln) => {
              const color = lector ? colorPresion(presionDe(ln.presion, lector), e.escala_bar) : null;
              return (
                <g key={ln.id} stroke={color ?? "currentColor"} strokeWidth={color ? LINEA_VIVA_MM : TINTA_MM}>
                  {ln.tramos.map(([x1, y1, x2, y2], i) => <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} />)}
                </g>
              );
            })}
          </g>
          {activas.length > 0 && (
            <g className="nm-posiciones">
              {activas.map(([d, c]) => <rect key={d} x={c[0]} y={c[1]} width={c[2]} height={c[3]} />)}
            </g>
          )}
          <g className="nm-textos">
            {e.textos.filter((t) => t.clase !== "detalle").map((t, i) => (
              <text key={i} x={t.x} y={t.y} fontSize={altoTexto(t.alto, k)} textAnchor={t.anclaje}>{t.texto}</text>
            ))}
          </g>
          <g className="nm-simbolos">
            {e.simbolos.map((s) => {
              const [x, y, w, h] = s.caja;
              const elegido = elegidos.has(s.designacion);
              return (
                <rect key={s.designacion} x={x - HOLGURA_MM} y={y - HOLGURA_MM} width={w + 2 * HOLGURA_MM}
                  height={h + 2 * HOLGURA_MM} rx={1.2} className={`nm-hit${elegido ? " elegido" : ""}`}
                  role="button" tabIndex={0} aria-pressed={elegido}
                  aria-label={`${nombreEnLinea(conNombre(s.designacion, nombres))}${s.piezas.length ? ": encontrarlo en el 3D" : ""}`}
                  onClick={() => onElegir(s)} onKeyDown={(ev) => tecla(ev, s)} />
              );
            })}
          </g>
        </svg>
      </div>
      {elegidosSim.map((s) => (
        <p key={s.designacion} className="nm-elegido cabeza-aparato" aria-live="polite">
          <NombreAparato a={conNombre(s.designacion, nombres)} detalle={detalleSimbolo(s)} />
        </p>
      ))}
      {lector && <Leyenda escala={e.escala_bar} />}
    </>
  );
}

/** La escala de la presión con su leyenda (la excepción de color por dato lleva siempre la suya). */
export function Leyenda({ escala }: { escala: number }) {
  const tope = topeLeyenda(escala);
  return (
    <div className="nm-leyenda" role="img" aria-label={`Presión de las líneas: gris sin aire; de azul oscuro a claro, hasta ${tope}`}>
      <span className="nm-leyenda-titulo">Presión</span>
      <span className="nm-rampa" aria-hidden="true">
        <span className="nm-sin-aire" style={{ background: SIN_PRESION }} />
        {RAMPA_PRESION.map((c) => <span key={c} style={{ background: c }} />)}
      </span>
      <span className="nm-leyenda-cifras" aria-hidden="true">
        <span>sin aire</span>
        <span>{tope}</span>
      </span>
    </div>
  );
}
