/* La historia de las señales de la sesión viva para el osciloscopio (plan V8.4 D6): un anillo
   de tamaño fijo (60 s a 30 fotogramas por segundo, con holgura) con el tiempo virtual y una
   columna Float32 por señal. Guarda TODAS las señales numéricas que llegan, así una señal que
   se suma al osciloscopio ya trae su pasado. Sin asignaciones por fotograma. Puro. */

/** Muestras del anillo: 60 s × 30 Hz = 1800, con holgura. */
export const CAPACIDAD = 2048;

export class Historia {
  readonly cap: number;
  /** Tiempo virtual de cada muestra (s). */
  readonly t: Float64Array;
  /** Una columna por señal, NaN donde ese fotograma no la trajo. */
  readonly cols = new Map<string, Float32Array>();
  /** Muestras válidas (≤ cap) y la posición de la más vieja. */
  n = 0;
  cabeza = 0;

  constructor(cap = CAPACIDAD) {
    this.cap = cap;
    this.t = new Float64Array(cap);
  }

  limpiar(): void {
    this.n = 0;
    this.cabeza = 0;
    this.cols.clear();
  }

  /** Índice físico de la k-ésima muestra (0 = la más vieja). */
  pos(k: number): number {
    return (this.cabeza + k) % this.cap;
  }

  /** Suma una muestra. `nombres[k]` ↔ `valores[k]`; un nombre sin columna la crea en NaN. Un
   *  tiempo que no avanza se descarta. */
  empujar(t: number, nombres: readonly (string | undefined)[], valores: ArrayLike<number>): void {
    if (this.n && !(t > this.t[this.pos(this.n - 1)])) return;
    let i: number;
    if (this.n < this.cap) {
      i = this.pos(this.n);
      this.n++;
    } else {
      i = this.cabeza;
      this.cabeza = (this.cabeza + 1) % this.cap;
    }
    this.t[i] = t;
    for (const col of this.cols.values()) col[i] = NaN;
    const m = Math.min(nombres.length, valores.length);
    for (let k = 0; k < m; k++) {
      const nombre = nombres[k];
      if (nombre === undefined) continue;
      let col = this.cols.get(nombre);
      if (!col) {
        col = new Float32Array(this.cap).fill(NaN);
        this.cols.set(nombre, col);
      }
      col[i] = valores[k];
    }
  }

  tPrimero(): number | null {
    return this.n ? this.t[this.cabeza] : null;
  }

  tUltimo(): number | null {
    return this.n ? this.t[this.pos(this.n - 1)] : null;
  }

  /** La primera muestra con t ≥ `t` (búsqueda binaria; `n` si no hay). */
  desde(t: number): number {
    let lo = 0;
    let hi = this.n;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (this.t[this.pos(mid)] < t) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  /** El valor de una señal en la k-ésima muestra (NaN si no hay). */
  valor(senal: string, k: number): number {
    const col = this.cols.get(senal);
    return col ? col[this.pos(k)] : NaN;
  }

  /** El último valor finito de una señal hasta la muestra k (inclusive), o NaN. */
  ultimoHasta(senal: string, k: number): number {
    const col = this.cols.get(senal);
    if (!col) return NaN;
    for (let j = Math.min(k, this.n - 1); j >= 0; j--) {
      const v = col[this.pos(j)];
      if (!Number.isNaN(v)) return v;
    }
    return NaN;
  }
}

/** Una copia congelada de una ventana (lo que el osciloscopio muestra tras el disparo). */
export interface Captura {
  t: Float64Array;
  cols: Map<string, Float32Array>;
}

/** Copia las muestras con t en [t0, t1] de las señales pedidas. */
export function capturar(h: Historia, senales: readonly string[], t0: number, t1: number): Captura {
  const a = h.desde(t0);
  let b = h.desde(t1);
  if (b < h.n && h.t[h.pos(b)] === t1) b++;
  const n = Math.max(0, b - a);
  const t = new Float64Array(n);
  const cols = new Map<string, Float32Array>();
  for (let k = 0; k < n; k++) t[k] = h.t[h.pos(a + k)];
  for (const s of senales) {
    const col = new Float32Array(n);
    for (let k = 0; k < n; k++) col[k] = h.valor(s, a + k);
    cols.set(s, col);
  }
  return { t, cols };
}
