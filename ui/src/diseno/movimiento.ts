/* Movimiento de la UI (plan V8.5 D14, F3b-0): las mismas duraciones y la misma curva que los
   tokens `--mov-rapido`, `--mov-normal` y `--curva-suave` de styles.css, para lo que se anima
   desde JavaScript (el vuelo de la cámara). Se anima sólo lo que orienta, nada rebota, y con
   `prefers-reduced-motion` se salta al final. Puro, salvo `movimientoReducido`. */

/** `--mov-rapido` (hover, aparecer un ítem). */
export const MOV_RAPIDO_MS = 160;
/** `--mov-normal` (abrir, plegar, encuadrar). */
export const MOV_NORMAL_MS = 320;

/** Puntos de control de `--curva-suave`: cubic-bezier(0.4, 0, 0.2, 1), arranca y frena suave. */
export const CURVA_SUAVE: readonly [number, number, number, number] = [0.4, 0, 0.2, 1];

/** Un cubic-bezier de CSS como función de [0, 1] → [0, 1]: la x es el tiempo, la y el avance. */
export function curvaBezier(x1: number, y1: number, x2: number, y2: number): (t: number) => number {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const x = (s: number) => ((ax * s + bx) * s + cx) * s;
  const dx = (s: number) => (3 * ax * s + 2 * bx) * s + cx;
  const y = (s: number) => ((ay * s + by) * s + cy) * s;
  return (t: number) => {
    if (!(t > 0)) return 0;
    if (t >= 1) return 1;
    let s = t; // Newton sobre x(s) = t; si la derivada se anula, bisección
    for (let i = 0; i < 8; i++) {
      const e = x(s) - t;
      if (Math.abs(e) < 1e-6) return y(s);
      const d = dx(s);
      if (Math.abs(d) < 1e-6) break;
      s -= e / d;
    }
    let lo = 0, hi = 1;
    s = t;
    for (let i = 0; i < 30; i++) {
      if (x(s) < t) lo = s; else hi = s;
      s = (lo + hi) / 2;
    }
    return y(s);
  };
}

/** La curva de `--curva-suave`. */
export const suave = curvaBezier(...CURVA_SUAVE);

/** La persona pidió menos movimiento al sistema: lo que se anima, salta. */
export function movimientoReducido(): boolean {
  try {
    return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}
