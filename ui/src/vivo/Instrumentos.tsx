import { useEffect, useRef } from "react";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import { segundos } from "../viewport/marcha/serie";
import { dibujarOsciloscopio, type Carril, type Tinta } from "./dibujoOsciloscopio";
import { useVivo } from "./estado";
import {
  alternarMultimetro, configurarDisparo, historia, quitarDelOsciloscopio, rearmar, useInstrumentos,
} from "./medicion";
import { ANCHOS, fuenteCaptura, fuenteHistoria, ventana, type Flanco } from "./osciloscopio";
import { colorDato } from "./paleta";
import { useTiposPlc } from "./tiposPlc";
import { leerValor, medidaDe } from "./unidades";
import "./instrumentos.css";

/* Los instrumentos de la sesión viva sobre el 3D (plan V8.4 D6 y D7), arriba de la barra de la
   sesión: el MULTÍMETRO (la señal anclada, en grande) y el OSCILOSCOPIO (las señales elegidas en
   el tiempo, un carril por señal, con disparo por flanco). Se eligen en el panel «Señales». El
   canvas se redibuja con su propio bucle a ≤ 30 cuadros por segundo, sin pasar por React. */

const CUADRO_MS = 1000 / 30;

export default function Instrumentos() {
  const hayTrazos = useInstrumentos((s) => s.trazos.length > 0);
  const multimetro = useInstrumentos((s) => s.multimetro);
  const plegado = useInstrumentos((s) => s.plegado);
  if (!hayTrazos && !multimetro) return null;
  return (
    <div className={`instrumentos${plegado ? " plegado" : ""}`} role="region" aria-label="Instrumentos">
      {multimetro && <Multimetro senal={multimetro} />}
      {hayTrazos && <Osciloscopio />}
    </div>
  );
}

function Multimetro({ senal }: { senal: string }) {
  const v = useVivo((s) => s.lecturas[senal]);
  const tipos = useTiposPlc();
  const m = medidaDe(senal, tipos.get(senal));
  const texto = leerValor(v, m);
  const corte = m.unidad && texto.endsWith(` ${m.unidad}`) ? texto.length - m.unidad.length - 1 : texto.length;
  return (
    <section className="multimetro" aria-label={`Multímetro: ${senal}`}>
      <header>
        <h3>Multímetro</h3>
        <button type="button" className="inst-icono" aria-label="Soltar la señal del multímetro" title="Soltar"
          onClick={() => alternarMultimetro(senal)}>
          <X size={14} />
        </button>
      </header>
      <span className="mm-senal">{senal}</span>
      <span className="mm-valor" aria-live="off">
        {texto.slice(0, corte)}
        {corte < texto.length && <small>{texto.slice(corte)}</small>}
      </span>
    </section>
  );
}

function tinta(): Tinta {
  const css = getComputedStyle(document.documentElement);
  const v = (n: string, def: string) => css.getPropertyValue(n).trim() || def;
  return { texto: v("--text", "#dfe4ec"), tenue: v("--muted", "#8b93a3"), linea: v("--border", "#2f3542"), fondo: v("--bg", "#121419") };
}

function Osciloscopio() {
  const trazos = useInstrumentos((s) => s.trazos);
  const ancho = useInstrumentos((s) => s.ancho);
  const plegado = useInstrumentos((s) => s.plegado);
  const aviso = useInstrumentos((s) => s.aviso);
  const set = useInstrumentos((s) => s.set);
  const tipos = useTiposPlc();
  const canvas = useRef<HTMLCanvasElement>(null);
  const puntero = useRef<number | null>(null);
  const alto = Math.min(320, Math.max(120, trazos.length * 62 + 18));

  useEffect(() => {
    const cv = canvas.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx || plegado) return;
    const colores = tinta();
    let raf = 0;
    let ultimo = -Infinity;
    const cuadro = (ahora: number) => {
      raf = requestAnimationFrame(cuadro);
      if (ahora - ultimo < CUADRO_MS - 2) return;
      ultimo = ahora;
      const dpr = window.devicePixelRatio || 1;
      const w = cv.clientWidth;
      const h = cv.clientHeight;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr);
        cv.height = Math.round(h * dpr);
      }
      const st = useInstrumentos.getState();
      const d = st.disparo;
      const f = d.captura ? fuenteCaptura(d.captura) : fuenteHistoria(historia);
      const conDisparo = d.estado === "disparado" || d.estado === "congelado";
      const [t0, t1] = ventana(st.ancho, historia.tUltimo(), conDisparo ? d.tDisparo : null);
      const carriles: Carril[] = st.trazos.map((x) => ({
        senal: x.senal, color: colorDato(x.color), medida: medidaDe(x.senal, tipos.get(x.senal)),
      }));
      dibujarOsciloscopio(ctx, w, h, dpr, f, carriles, t0, t1, colores, {
        disparo: d.senal && d.estado !== "apagado" ? { senal: d.senal, umbral: d.umbral, t: conDisparo ? d.tDisparo : null } : null,
        punteroX: puntero.current,
      });
    };
    raf = requestAnimationFrame(cuadro);
    return () => cancelAnimationFrame(raf);
  }, [plegado, tipos]);

  return (
    <section className="osciloscopio" aria-label="Osciloscopio">
      <header>
        <h3>Osciloscopio</h3>
        <select value={ancho} onChange={(e) => set({ ancho: Number(e.target.value) })} aria-label="Ventana de tiempo">
          {ANCHOS.map((a) => <option key={a} value={a}>{a} s</option>)}
        </select>
        <ControlDisparo />
        <span className="inst-espacio" />
        <button type="button" className="inst-icono" onClick={() => set({ plegado: !plegado })}
          aria-label={plegado ? "Mostrar los instrumentos" : "Plegar los instrumentos"} title={plegado ? "Mostrar" : "Plegar"}>
          {plegado ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </button>
      </header>
      {aviso && <p className="estado-aviso">{aviso}</p>}
      {!plegado && (
        <>
          <ul className="leyenda-osc" aria-label="Señales del osciloscopio">
            {trazos.map((x) => (
              <li key={x.senal}>
                <span className="muestra-color" style={{ background: colorDato(x.color) }} aria-hidden />
                {x.senal}
                <button type="button" className="inst-icono" aria-label={`Quitar ${x.senal} del osciloscopio`} title="Quitar"
                  onClick={() => quitarDelOsciloscopio(x.senal)}>
                  <X size={12} />
                </button>
              </li>
            ))}
          </ul>
          <canvas
            ref={canvas}
            className="lienzo-osc"
            style={{ height: alto }}
            role="img"
            aria-label={`Curvas de ${trazos.map((x) => x.senal).join(", ")}`}
            onPointerMove={(e) => {
              puntero.current = e.clientX - e.currentTarget.getBoundingClientRect().left;
            }}
            onPointerLeave={() => {
              puntero.current = null;
            }}
          />
        </>
      )}
    </section>
  );
}

function ControlDisparo() {
  const trazos = useInstrumentos((s) => s.trazos);
  const senal = useInstrumentos((s) => s.disparo.senal);
  const flanco = useInstrumentos((s) => s.disparo.flanco);
  const umbral = useInstrumentos((s) => s.disparo.umbral);
  const estado = useInstrumentos((s) => s.disparo.estado);
  const tDisparo = useInstrumentos((s) => s.disparo.tDisparo);
  const tipos = useTiposPlc();
  const enLista = senal !== null && trazos.some((x) => x.senal === senal);
  const unidad = senal ? medidaDe(senal, tipos.get(senal)).unidad : "";
  return (
    <div className="control-disparo" role="group" aria-label="Disparo">
      <select
        value={enLista ? senal! : ""}
        aria-label="Señal del disparo"
        onChange={(e) => {
          const s = e.target.value || null;
          const booleana = s ? medidaDe(s, tipos.get(s)).booleana : false;
          configurarDisparo({ senal: s, ...(booleana ? { umbral: 0.5 } : {}) });
        }}
      >
        <option value="">Sin disparo</option>
        {trazos.map((x) => <option key={x.senal} value={x.senal}>Disparo en {x.senal}</option>)}
      </select>
      {enLista && (
        <>
          <select value={flanco} aria-label="Flanco" onChange={(e) => configurarDisparo({ flanco: e.target.value as Flanco })}>
            <option value="subida">Subida</option>
            <option value="bajada">Bajada</option>
          </select>
          <label className="umbral-disparo">
            <span>Umbral</span>
            <input type="number" step="any" value={umbral} aria-label="Umbral del disparo"
              onChange={(e) => {
                const v = Number(e.target.value);
                if (Number.isFinite(v)) configurarDisparo({ umbral: v });
              }} />
            {unidad && <span>{unidad}</span>}
          </label>
          <span className="estado-disparo">
            {estado === "armado" ? "Esperando el flanco"
              : tDisparo !== null ? `Disparó a los ${segundos(tDisparo)}${estado === "congelado" ? " · quieto" : ""}` : ""}
          </span>
          {(estado === "disparado" || estado === "congelado") && (
            <button type="button" onClick={rearmar}>Re-armar</button>
          )}
        </>
      )}
    </div>
  );
}
