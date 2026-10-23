import type { Captura, Historia } from "./historia";

/* La lógica del osciloscopio de la sesión viva (plan V8.4 D6 y D7), sin canvas ni React: qué
   señales se dibujan y con qué color, la ventana de tiempo, la escala de cada señal y el
   disparo por flanco. Puro (se prueba en node). */

/** Caben 8 señales: los 8 colores de la paleta (`paleta.ts`); una novena no inventa un color. */
export const MAX_SENALES = 8;
/** Anchos de la ventana deslizante (s). */
export const ANCHOS = [10, 20, 30, 60] as const;
/** Fracción de la ventana ANTES del disparo (el resto queda para lo que pasó después). */
export const PRE_DISPARO = 0.25;

/** Una señal en el osciloscopio. `color` = su posición en la paleta: la conserva aunque se
 *  quiten otras (el color sigue a la señal, no a su orden). */
export interface Trazo {
  senal: string;
  color: number;
}

/** Suma una señal con el primer color libre. Ya estaba → igual; no cabe → null. */
export function sumarTrazo(trazos: readonly Trazo[], senal: string): Trazo[] | null {
  if (trazos.some((x) => x.senal === senal)) return [...trazos];
  if (trazos.length >= MAX_SENALES) return null;
  const usados = new Set(trazos.map((x) => x.color));
  let color = 0;
  while (usados.has(color)) color++;
  return [...trazos, { senal, color }];
}

export function quitarTrazo(trazos: readonly Trazo[], senal: string): Trazo[] {
  return trazos.filter((x) => x.senal !== senal);
}

// ── lo que se lee para dibujar: la historia viva o una captura congelada ────────────────────

export interface Fuente {
  n: number;
  tEn: (k: number) => number;
  valor: (senal: string, k: number) => number;
  /** Primera muestra con t ≥ `t`. */
  desde: (t: number) => number;
}

export function fuenteHistoria(h: Historia): Fuente {
  return { n: h.n, tEn: (k) => h.t[h.pos(k)], valor: (s, k) => h.valor(s, k), desde: (t) => h.desde(t) };
}

export function fuenteCaptura(c: Captura): Fuente {
  const n = c.t.length;
  return {
    n,
    tEn: (k) => c.t[k],
    valor: (s, k) => c.cols.get(s)?.[k] ?? NaN,
    desde: (t) => {
      let lo = 0;
      let hi = n;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (c.t[mid] < t) lo = mid + 1;
        else hi = mid;
      }
      return lo;
    },
  };
}

// ── escala por señal ─────────────────────────────────────────────────────────────────────────

export interface Escala {
  lo: number;
  hi: number;
}

/** La escala de una señal en la ventana: de su mínimo a su máximo con un margen; una señal
 *  sí/no va fija de 0 a 1; una constante, centrada con un alto mínimo. Sin datos: 0–1. */
export function escalaDe(f: Fuente, senal: string, k0: number, k1: number, booleana: boolean): Escala {
  if (booleana) return { lo: -0.15, hi: 1.15 };
  let lo = Infinity;
  let hi = -Infinity;
  for (let k = k0; k < k1; k++) {
    const v = f.valor(senal, k);
    if (!Number.isFinite(v)) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (lo > hi) return { lo: 0, hi: 1 };
  const alto = hi - lo;
  if (alto < 1e-9 * Math.max(1, Math.abs(hi))) {
    const m = Math.max(1, Math.abs(hi) * 0.1);
    return { lo: lo - m, hi: hi + m };
  }
  return { lo: lo - alto * 0.08, hi: hi + alto * 0.08 };
}

// ── la ventana ───────────────────────────────────────────────────────────────────────────────

/** [t0, t1] que se ve: deslizante (termina en la última muestra) o alrededor del disparo. */
export function ventana(ancho: number, tUltimo: number | null, tDisparo?: number | null): [number, number] {
  if (tDisparo !== undefined && tDisparo !== null) {
    const t0 = tDisparo - ancho * PRE_DISPARO;
    return [t0, t0 + ancho];
  }
  const t1 = tUltimo ?? 0;
  return [t1 - ancho, t1];
}

// ── disparo por flanco ───────────────────────────────────────────────────────────────────────

export type Flanco = "subida" | "bajada";
/** apagado: corre libre · armado: espera el flanco · disparado: junta lo que pasa después ·
 *  congelado: la ventana alrededor del disparo quedó fija (se re-arma con un botón). */
export type EstadoDisparo = "apagado" | "armado" | "disparado" | "congelado";

export function cruza(antes: number, ahora: number, umbral: number, flanco: Flanco): boolean {
  if (!Number.isFinite(antes) || !Number.isFinite(ahora)) return false;
  return flanco === "subida" ? antes < umbral && ahora >= umbral : antes > umbral && ahora <= umbral;
}

/** El primer cruce del umbral con ese flanco en las muestras k ≥ `desdeK` (comparando con la
 *  muestra válida anterior), con su tiempo interpolado; null si no hay. */
export function buscarDisparo(f: Fuente, senal: string, umbral: number, flanco: Flanco, desdeK = 0): number | null {
  let kPrev = -1;
  let vPrev = NaN;
  for (let k = Math.max(0, desdeK - 1); k < f.n; k++) {
    const v = f.valor(senal, k);
    if (!Number.isFinite(v)) continue;
    if (kPrev >= 0 && k >= desdeK && cruza(vPrev, v, umbral, flanco)) {
      const t0 = f.tEn(kPrev);
      const t1 = f.tEn(k);
      const r = (umbral - vPrev) / (v - vPrev);
      return t0 + (t1 - t0) * Math.min(1, Math.max(0, r));
    }
    kPrev = k;
    vPrev = v;
  }
  return null;
}

/** Ticks del eje de tiempo: un paso «redondo» (1, 2, 5 × 10ⁿ s) que deja ~6 marcas. */
export function ticksTiempo(t0: number, t1: number, marcas = 6): number[] {
  const ancho = t1 - t0;
  if (!(ancho > 0)) return [];
  const crudo = ancho / marcas;
  const p = 10 ** Math.floor(Math.log10(crudo));
  const paso = [1, 2, 5, 10].map((m) => m * p).find((x) => x >= crudo) ?? 10 * p;
  const out: number[] = [];
  for (let t = Math.ceil(t0 / paso) * paso; t <= t1 + 1e-9; t += paso) out.push(Math.round(t / paso) * paso);
  return out;
}
