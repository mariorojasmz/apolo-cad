import { create } from "zustand";
import { capturar, Historia, type Captura } from "./historia";
import {
  buscarDisparo, fuenteHistoria, quitarTrazo, sumarTrazo, ventana,
  type EstadoDisparo, type Flanco, type Trazo,
} from "./osciloscopio";

/* Los instrumentos de la sesión viva (plan V8.4 D6 y D7): el MULTÍMETRO (una señal anclada, su
   valor grande) y el OSCILOSCOPIO (hasta 8 señales en el tiempo, con disparo por flanco). Lo
   elige la persona en el árbol de señales (`PanelSenales.tsx`) y se dibuja en
   `Instrumentos.tsx`, sobre el 3D. La historia de TODAS las señales vive aquí (fuera de React):
   `sesion.ts` le pasa cada fotograma con `registrarMuestra`, que también vigila el disparo. */

export const historia = new Historia();

export interface Disparo {
  senal: string | null;
  flanco: Flanco;
  umbral: number;
  estado: EstadoDisparo;
  /** Desde qué tiempo virtual se busca el flanco (lo de antes de armar no dispara). */
  armadoEn: number;
  tDisparo: number | null;
  /** La ventana congelada alrededor del disparo. */
  captura: Captura | null;
}

export interface EstadoInstrumentos {
  trazos: Trazo[];
  multimetro: string | null;
  ancho: number;
  disparo: Disparo;
  /** El último aviso (una señal que no cupo). */
  aviso: string | null;
  /** El panel de instrumentos plegado (queda sólo su cabecera). */
  plegado: boolean;
  set: (p: Partial<EstadoInstrumentos>) => void;
}

export const DISPARO_INICIAL: Disparo = {
  senal: null, flanco: "subida", umbral: 0.5, estado: "apagado", armadoEn: 0, tDisparo: null, captura: null,
};

export const useInstrumentos = create<EstadoInstrumentos>((set) => ({
  trazos: [],
  multimetro: null,
  ancho: 20,
  disparo: DISPARO_INICIAL,
  aviso: null,
  plegado: false,
  set: (p) => set(p),
}));

const st = () => useInstrumentos.getState();

/** Suma una señal al osciloscopio (o la quita si ya estaba). */
export function alternarOsciloscopio(senal: string): void {
  const { trazos } = st();
  if (trazos.some((x) => x.senal === senal)) {
    quitarDelOsciloscopio(senal);
    return;
  }
  const nuevos = sumarTrazo(trazos, senal);
  if (!nuevos) {
    st().set({ aviso: "Caben 8 señales en el osciloscopio: quita una para sumar otra." });
    return;
  }
  st().set({ trazos: nuevos, aviso: null, plegado: false });
}

export function quitarDelOsciloscopio(senal: string): void {
  st().set({ trazos: quitarTrazo(st().trazos, senal), aviso: null });
  if (st().disparo.senal === senal) configurarDisparo({ senal: null }); // sin su señal, no hay disparo
}

/** Ancla una señal al multímetro (otra vez la misma = la suelta). */
export function alternarMultimetro(senal: string): void {
  st().set({ multimetro: st().multimetro === senal ? null : senal, plegado: false });
}

/** Configura el disparo y lo arma (espera el flanco desde ahora). `senal` null = apagado. */
export function configurarDisparo(p: Partial<Pick<Disparo, "senal" | "flanco" | "umbral">>): void {
  const d = { ...st().disparo, ...p };
  st().set({ disparo: d.senal ? armado(d) : { ...d, estado: "apagado", tDisparo: null, captura: null } });
}

export function rearmar(): void {
  const d = st().disparo;
  if (d.senal) st().set({ disparo: armado(d) });
}

function armado(d: Disparo): Disparo {
  return { ...d, estado: "armado", armadoEn: historia.tUltimo() ?? 0, tDisparo: null, captura: null };
}

/** Un fotograma nuevo: a la historia, y el disparo avanza (armado → disparado → congelado). */
export function registrarMuestra(t: number, nombres: readonly (string | undefined)[], valores: ArrayLike<number>): void {
  historia.empujar(t, nombres, valores);
  avanzarDisparo();
}

/** La historia de una sesión nueva empieza vacía; un disparo armado se re-arma en ella. */
export function reiniciarHistoria(): void {
  historia.limpiar();
  const d = st().disparo;
  st().set({ disparo: d.senal ? { ...armado(d), armadoEn: 0 } : d });
}

function avanzarDisparo(): void {
  const s = st();
  const d = s.disparo;
  if (!d.senal || d.estado === "apagado" || d.estado === "congelado") return;
  if (d.estado === "armado") {
    const f = fuenteHistoria(historia);
    // sólo lo nuevo: las dos últimas muestras con valor (la anterior + la de ahora)
    const desde = Math.max(f.desde(d.armadoEn), f.n - 1);
    const t = buscarDisparo(f, d.senal, d.umbral, d.flanco, desde);
    if (t === null) return;
    s.set({ disparo: { ...d, estado: "disparado", tDisparo: t } });
    return;
  }
  // disparado: cuando ya pasó toda la ventana después del disparo, se congela
  const tU = historia.tUltimo();
  const [t0, t1] = ventana(s.ancho, tU, d.tDisparo);
  if (tU !== null && tU >= t1) {
    // todas las señales: una que se sume después del disparo también se ve en la captura
    s.set({ disparo: { ...d, estado: "congelado", captura: capturar(historia, [...historia.cols.keys()], t0, t1) } });
  }
}
