import type { Pantalla3D, TemaPantalla } from "../extensiones/tipos";
import type { DispositivoVivo } from "./protocolo";

/* La lógica PURA de las pantallas 3D de las extensiones (plan plc-en-el-lazo, D13 b): qué
   dispositivo lleva qué pantalla, en qué cara de su pieza va el plano, de qué tamaño y cómo un
   toque (uv del raycast) se vuelve un píxel del canvas. Sin three.js ni DOM: `pantallas3d.ts` lo
   instala en el visor.

   La cara frontal se busca en la GEOMETRÍA de la pieza (su marco: el de la definición si es una
   instancia, el del mundo si no), sin convención de ejes: es la cara plana extrema más grande. Un
   aparato de puerta en un recorte tiene el frente más grande que su cuerpo (el panel de 7″: marco
   200 × 146 mm delante, cuerpo 190 × 136 detrás; D12), así que gana su frente aunque la pieza esté
   girada. Si empatan (una placa lisa), gana la que mira más hacia −Y del mundo: la vista «frente»
   de Apolo, donde va la puerta de un tablero sin girar. */

export type Tripla = [number, number, number];

export interface CaraFrontal {
  /** Centro de la cara, en el marco de la geometría (mm). */
  centro: Tripla;
  /** Normal hacia afuera; `u` a la derecha y `v` arriba, vista desde afuera (u × v = normal). */
  normal: Tripla;
  u: Tripla;
  v: Tripla;
  ancho: number;
  alto: number;
}

const dot = (a: Tripla, b: Tripla) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cruz = (a: Tripla, b: Tripla): Tripla => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const escalar = (a: Tripla, k: number): Tripla => [a[0] * k, a[1] * k, a[2] * k];
const unitario = (a: Tripla): Tripla => {
  const n = Math.hypot(a[0], a[1], a[2]);
  return n > 0 ? escalar(a, 1 / n) : [0, 0, 0];
};

/** Una dirección del marco de la geometría llevada al mundo por la matriz 4×4 columna-mayor. */
export function alMundo(m: ArrayLike<number> | null | undefined, d: Tripla): Tripla {
  if (!m) return d;
  return [m[0] * d[0] + m[4] * d[1] + m[8] * d[2], m[1] * d[0] + m[5] * d[1] + m[9] * d[2],
    m[2] * d[0] + m[6] * d[1] + m[10] * d[2]];
}

const PARALELO = 0.999;

interface Grupo { n: Tripla; tris: { d: number; area: number; i: number }[] }

/** La cara frontal de una pieza a partir de su malla (posiciones xyz planas; índices o null si no
   es indexada) y de la matriz que la lleva al mundo (columna-mayor; null = ya está en el mundo).
   `arriba` (mundo) orienta la cara: `v` es el eje de la cara que más sube. null si no hay caras. */
export function caraFrontal(pos: ArrayLike<number>, indices: ArrayLike<number> | null,
  matriz: ArrayLike<number> | null = null, arriba: Tripla = [0, 0, 1]): CaraFrontal | null {
  const nv = Math.floor(pos.length / 3);
  const nt = indices ? Math.floor(indices.length / 3) : Math.floor(nv / 3);
  const vert = (k: number): Tripla => [pos[3 * k], pos[3 * k + 1], pos[3 * k + 2]];
  const idx = (t: number, j: number) => (indices ? indices[3 * t + j] : 3 * t + j);
  let diag = 0;
  {
    const lo: Tripla = [Infinity, Infinity, Infinity], hi: Tripla = [-Infinity, -Infinity, -Infinity];
    for (let k = 0; k < nv; k++) for (let j = 0; j < 3; j++) {
      lo[j] = Math.min(lo[j], pos[3 * k + j]);
      hi[j] = Math.max(hi[j], pos[3 * k + j]);
    }
    if (nv) diag = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]);
  }
  const tol = Math.max(0.05, diag * 1e-3);
  // triángulos agrupados por dirección de su normal
  const grupos: Grupo[] = [];
  for (let t = 0; t < nt; t++) {
    const a = vert(idx(t, 0)), b = vert(idx(t, 1)), c = vert(idx(t, 2));
    const x = cruz([b[0] - a[0], b[1] - a[1], b[2] - a[2]], [c[0] - a[0], c[1] - a[1], c[2] - a[2]]);
    const doble = Math.hypot(x[0], x[1], x[2]);
    if (doble < 1e-9) continue;
    const n = escalar(x, 1 / doble);
    const g = grupos.find((gr) => dot(gr.n, n) > PARALELO) ?? (grupos.push({ n, tris: [] }), grupos[grupos.length - 1]);
    g.tris.push({ d: dot(n, a), area: doble / 2, i: t });
  }
  if (!grupos.length) return null;
  // por dirección, el área del plano EXTREMO de toda la pieza en ese sentido
  const candidatos = grupos.map((g) => {
    let ext = -Infinity;
    for (let k = 0; k < nv; k++) ext = Math.max(ext, dot(g.n, vert(k)));
    const tris = g.tris.filter((tr) => Math.abs(tr.d - ext) <= tol);
    return { g, ext, tris, area: tris.reduce((s, tr) => s + tr.area, 0) };
  }).filter((c) => c.area > 0);
  if (!candidatos.length) return null;
  candidatos.sort((a, b) => b.area - a.area);
  let frente = candidatos[0];
  const empate = candidatos.find((c) => c !== frente && c.area >= frente.area * 0.98);
  if (empate && alMundo(matriz, empate.g.n)[1] < alMundo(matriz, frente.g.n)[1] - 1e-6) frente = empate;
  const n = frente.g.n;
  // los ejes de la cara: el de un costado (una normal perpendicular) o, si no hay, la arista más larga
  const lado = grupos.find((g) => Math.abs(dot(g.n, n)) < 1 - PARALELO);
  let e1: Tripla;
  if (lado) e1 = lado.n;
  else {
    let mejor: Tripla = [1, 0, 0], largo = -1;
    for (const tr of frente.tris) for (let j = 0; j < 3; j++) {
      const a = vert(idx(tr.i, j)), b = vert(idx(tr.i, (j + 1) % 3));
      const e: Tripla = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
      const l = Math.hypot(e[0], e[1], e[2]);
      if (l > largo) { largo = l; mejor = e; }
    }
    e1 = mejor;
  }
  e1 = unitario(cruz(cruz(n, e1), n)); // sin componente normal
  const e2 = cruz(n, e1);
  // v = el eje que más sube en el mundo (si la cara mira arriba o abajo, el que más va hacia +Y)
  const sube = (e: Tripla) => dot(unitario(alMundo(matriz, e)), arriba);
  let v: Tripla;
  if (Math.max(Math.abs(sube(e1)), Math.abs(sube(e2))) > 1e-3) {
    v = Math.abs(sube(e1)) >= Math.abs(sube(e2)) ? e1 : e2;
    if (sube(v) < 0) v = escalar(v, -1);
  } else {
    const haciaY = (e: Tripla) => unitario(alMundo(matriz, e))[1];
    v = Math.abs(haciaY(e1)) >= Math.abs(haciaY(e2)) ? e1 : e2;
    if (haciaY(v) < 0) v = escalar(v, -1);
  }
  const u = cruz(v, n);
  let u0 = Infinity, u1 = -Infinity, v0 = Infinity, v1 = -Infinity;
  for (const tr of frente.tris) for (let j = 0; j < 3; j++) {
    const p = vert(idx(tr.i, j));
    const pu = dot(p, u), pv = dot(p, v);
    u0 = Math.min(u0, pu); u1 = Math.max(u1, pu); v0 = Math.min(v0, pv); v1 = Math.max(v1, pv);
  }
  const cu = (u0 + u1) / 2, cv = (v0 + v1) / 2;
  const centro: Tripla = [0, 1, 2].map((j) => u[j] * cu + v[j] * cv + n[j] * frente.ext) as Tripla;
  return { centro, normal: n, u, v, ancho: u1 - u0, alto: v1 - v0 };
}

/** La rígida 4×4 (columna-mayor) que lleva un plano XY centrado en el origen a la cara: x → u,
   y → v, z → normal, `separacion` mm por delante (para que gane al raycast y no parpadee). */
export function matrizDeCara(c: CaraFrontal, separacion = 0.4): number[] {
  const o = [0, 1, 2].map((j) => c.centro[j] + c.normal[j] * separacion);
  return [...c.u, 0, ...c.v, 0, ...c.normal, 0, o[0], o[1], o[2], 1];
}

/** Píxeles por mm de una pantalla que no declara su resolución. */
const PX_POR_MM = 4;

/** El rectángulo de la pantalla dentro de una cara: con la resolución del dispositivo, su
   proporción encajada en el `margen` de la cara (un panel tiene marco alrededor del vidrio); sin
   ella, toda la cara (al margen) a 4 px/mm, entre 64 y 2048 px. */
export function rectanguloPantalla(ancho: number, alto: number, px?: readonly [number, number] | null,
  margen = 0.82): { ancho: number; alto: number; px: [number, number] } {
  const aw = ancho * margen, ah = alto * margen;
  if (px && px[0] > 0 && px[1] > 0) {
    const k = Math.min(aw / px[0], ah / px[1]);
    return { ancho: px[0] * k, alto: px[1] * k, px: [Math.round(px[0]), Math.round(px[1])] };
  }
  const lim = (x: number) => Math.max(64, Math.min(2048, Math.round(x * PX_POR_MM)));
  return { ancho: aw, alto: ah, px: [lim(aw), lim(ah)] };
}

/** El píxel del canvas (origen arriba a la izquierda) que corresponde a la uv de un toque en el
   plano (uv de `PlaneGeometry`: (0, 0) abajo a la izquierda). */
export function uvAPx(uv: { x: number; y: number }, px: readonly [number, number]): { x: number; y: number } {
  const [w, h] = px;
  return {
    x: Math.min(w - 1, Math.max(0, Math.floor(uv.x * w))),
    y: Math.min(h - 1, Math.max(0, Math.floor((1 - uv.y) * h))),
  };
}

/** Cada dispositivo de la tabla con pieza en el 3D y una pantalla para su `tipo`. */
export function pantallasDeLaSesion(dispositivos: readonly DispositivoVivo[], pantallas: readonly Pantalla3D[],
  hayPieza: (id: string) => boolean): { dispositivo: DispositivoVivo; pantalla: Pantalla3D }[] {
  const out: { dispositivo: DispositivoVivo; pantalla: Pantalla3D }[] = [];
  for (const d of dispositivos) {
    const pantalla = pantallas.find((p) => p.tipo === d.tipo);
    if (pantalla && d.pieza && hayPieza(d.pieza)) out.push({ dispositivo: d, pantalla });
  }
  return out;
}

/** Los colores del tema para un canvas, de los tokens de `styles.css` (`leer("--panel")`); un token
   que falta cae al valor del tema oscuro. */
export function temaDe(leer: (token: string) => string, fuente = ""): TemaPantalla {
  const t = (token: string, defecto: string) => leer(token).trim() || defecto;
  return {
    fondo: t("--bg", "#121419"), panel: t("--panel", "#1e222b"), texto: t("--text", "#dfe4ec"),
    tenue: t("--muted", "#8b93a3"), acento: t("--accent", "#5b8cff"), borde: t("--border", "#2f3542"),
    fuente: fuente.trim() || "system-ui, sans-serif",
  };
}
