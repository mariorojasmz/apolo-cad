import { PARTES_3D, tramoDe, type PlanGuion } from "../planGuion";

/* Los dos niveles del video y la foto realista (plan video-realista, D6). Puro: sin three ni DOM.

   - **rápido** (por defecto): el visor «alta» con el antialias acumulado (`acumulado.ts`).
   - **máximo**: trazado de rayos con `three-gpu-pathtracer` 0.0.23 (`trazador.ts`), N muestras
     por cuadro + el denoiser. Mario (2026-10-20): «no es viable ahora, pero igual lo quiero»: queda
     disponible, nunca por defecto. La foto realista del visor siempre es de este nivel.

   La SEMILLA fija el ruido: la misma pose con la misma semilla da la misma imagen. En el video,
   todos los cuadros usan la misma semilla (el grano queda quieto en la pantalla en vez de
   hervir entre cuadros) salvo `semillaPorCuadro`. */

export type Nivel = "rapido" | "maximo";
export const NIVEL_POR_DEFECTO: Nivel = "rapido";

/** El denoiser de la librería (glslSmartDeNoise): `sigma` px de radio × `kSigma`; `umbral` es la
   diferencia de color (lineal) que ya se considera un borde y no se suaviza. */
export interface Denoise {
  sigma: number;
  kSigma: number;
  umbral: number;
}

export interface OpcionesTrazado {
  /** Muestras por píxel de cada cuadro. */
  muestras: number;
  semilla: number;
  /** En el video: una semilla distinta por cuadro (grano que cambia) en vez de la misma. */
  semillaPorCuadro: boolean;
  /** Rebotes de cada camino. */
  rebotes: number;
  /** El cuadro se dibuja en teselas × teselas pedazos: cada llamada a la GPU es corta y el hilo
     se suelta entre pedazos (una llamada de varios segundos puede reiniciar el driver). */
  teselas: number;
  denoise: Denoise | null;
}

export const DENOISE: Denoise = { sigma: 2.5, kSigma: 1.5, umbral: 0.08 };

/** Video de noche. Medido en F4 (bitácora, piloto 74 a 1080p con el denoiser): con 16 muestras
   quedan chispas; con 64 casi limpio (alguna en la guarda); 128 es el margen para que el grano no
   titile entre cuadros. ~0,3 s por muestra en una Intel UHD: ~40 s por cuadro. */
export const TRAZADO_VIDEO: OpcionesTrazado = {
  muestras: 128, semilla: 1, semillaPorCuadro: false, rebotes: 5, teselas: 2, denoise: DENOISE,
};

/** La foto: una sola imagen, limpia con 256 (~80 s de trazado en una Intel UHD a 1080p). */
export const TRAZADO_FOTO: OpcionesTrazado = { ...TRAZADO_VIDEO, muestras: 256 };

const LIMITES = { muestras: [1, 8192], rebotes: [1, 16], teselas: [1, 8] } as const;

const entero = (v: unknown, def: number, [min, max]: readonly [number, number]) => {
  const n = typeof v === "number" && Number.isFinite(v) ? Math.round(v) : def;
  return Math.min(Math.max(n, min), max);
};

/** Las opciones de `base` con lo que se pidió encima, acotadas a valores que no cuelgan la GPU. */
export function opcionesTrazado(base: OpcionesTrazado, pedido: Partial<OpcionesTrazado> = {}): OpcionesTrazado {
  const semilla = typeof pedido.semilla === "number" && Number.isFinite(pedido.semilla)
    ? Math.abs(Math.round(pedido.semilla)) % 2 ** 31 : base.semilla;
  const d = pedido.denoise === undefined ? base.denoise : pedido.denoise;
  return {
    muestras: entero(pedido.muestras, base.muestras, LIMITES.muestras),
    semilla,
    semillaPorCuadro: pedido.semillaPorCuadro ?? base.semillaPorCuadro,
    rebotes: entero(pedido.rebotes, base.rebotes, LIMITES.rebotes),
    teselas: entero(pedido.teselas, base.teselas, LIMITES.teselas),
    denoise: d && d.sigma > 0 && d.kSigma > 0 && d.umbral > 0 ? { ...d } : null,
  };
}

/** Números en [0, 1) con semilla (mulberry32): lo que el trazador usa en vez de `Math.random`
   para que su ruido no cambie entre una sesión y otra. */
export function aleatorioConSemilla(semilla: number): () => number {
  let s = semilla >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** La semilla del cuadro `n` del video. */
export function semillaDeCuadro(op: OpcionesTrazado, n: number): number {
  return op.semillaPorCuadro ? (op.semilla + n) % 2 ** 31 : op.semilla;
}

export function nivelDeTexto(s: string | null | undefined): Nivel | null {
  const t = (s ?? "").trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  return t === "rapido" || t === "maximo" ? t : null;
}

/** Lo que pide la URL de `publicar generar --render navegador --nivel maximo`
   (`?grabar=<sesion>&nivel=maximo&muestras=N&semilla=S`); null si no pide un nivel. */
export function pedidoDeUrl(busqueda: string): { nivel: Nivel; muestras?: number; semilla?: number } | null {
  const q = new URLSearchParams(busqueda);
  const nivel = nivelDeTexto(q.get("nivel"));
  if (!nivel) return null;
  const num = (k: string) => {
    const v = q.get(k);
    return v !== null && /^\d{1,7}$/.test(v) ? Number(v) : undefined;
  };
  const out: { nivel: Nivel; muestras?: number; semilla?: number } = { nivel };
  const muestras = num("muestras");
  const semilla = num("semilla");
  if (muestras !== undefined) out.muestras = muestras;
  if (semilla !== undefined) out.semilla = semilla;
  return out;
}

/** Tamaño de la foto: el MISMO encuadre que se ve en el visor (su proporción), con el lado mayor
   en `lado` px; pares, como pide el H.264 si la foto termina en un video. */
export function tamanoFoto(anchoVista: number, altoVista: number, lado = 1920): { ancho: number; alto: number } {
  const w = Math.max(1, anchoVista);
  const h = Math.max(1, altoVista);
  const par = (x: number) => Math.max(2, 2 * Math.round(x / 2));
  return w >= h ? { ancho: par(lado), alto: par((lado * h) / w) } : { ancho: par((lado * w) / h), alto: par(lado) };
}

/** Nombre del archivo de la foto: `foto-realista-<proyecto>-<aaaammdd-hhmmss>.png`. */
export function nombreFoto(proyecto: string | null, fecha = new Date()): string {
  const p = (proyecto ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
  const d = (n: number) => String(n).padStart(2, "0");
  const sello = `${fecha.getFullYear()}${d(fecha.getMonth() + 1)}${d(fecha.getDate())}-`
    + `${d(fecha.getHours())}${d(fecha.getMinutes())}${d(fecha.getSeconds())}`;
  return `foto-realista-${p ? `${p}-` : ""}${sello}.png`;
}

export interface PlanTrazado {
  cuadros: number;
  /** Cuadros 3D: los que pasan por el trazador (el resto son tarjetas de la API). */
  trazados: number;
  tarjetas: number;
}

/** Qué cuadros del guion se trazan: los de las partes 3D (etapas, marcha, vuelta). */
export function planTrazado(plan: Pick<PlanGuion, "cuadros" | "tramos">): PlanTrazado {
  let trazados = 0;
  for (const t of plan.tramos) if (PARTES_3D.has(t.parte)) trazados += t.fin - t.inicio;
  return { cuadros: plan.cuadros, trazados, tarjetas: plan.cuadros - trazados };
}

/** ¿El cuadro `n` del guion pasa por el trazador? */
export const seTraza = (plan: PlanGuion, n: number) => PARTES_3D.has(tramoDe(plan, n).parte);

/** Segundos estimados de grabar el plan con `sPorCuadro` en los cuadros trazados (las
   tarjetas cuestan ~`sTarjeta`: sólo la foto y la subida). */
export function estimarSegundos(p: PlanTrazado, sPorCuadro: number, sTarjeta = 0.05): number {
  return p.trazados * sPorCuadro + p.tarjetas * sTarjeta;
}
