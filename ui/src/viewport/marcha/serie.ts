import * as THREE from "three";

/* La marcha como SERIE DE TIEMPO (plan visor-realista, D4): el servidor simula y entrega poses a
   ~50 Hz (`GET /api/physics/dynamics/serie`, `physics/dinamica_serie.py`); el visor la reproduce
   a 60 fps interpolando entre dos muestras. Aquí, el formato y la interpolación (sin three.js de
   escena: se prueba en node). Poses = `x, y, z, qx, qy, qz, qw` (mm) aplanadas por muestra. */

export interface CuerpoSerie {
  junta: string;
  /** Piezas que mueve la junta (ids de la escena). */
  piezas: string[];
  /** Transformación RELATIVA a la pose inicial, T(t) = P(t)·P(0)⁻¹: se aplica sobre la malla de
   *  diseño de cada pieza. 7 números por muestra. */
  poses: number[];
}

export interface ProductoSerie {
  name: string;
  producto: string;
  dims_mm: [number, number, number];
  /** Primera muestra en la que existe (nace en su hora con `cada_s`). */
  desde: number;
  /** Pose ABSOLUTA del centro de la caja desde `desde`. 7 números por muestra. */
  poses: number[];
}

export interface BandaSerie {
  pieza: string;
  junta: string;
  radio_mm: number;
  /** Hacia dónde avanza la cara superior con velocidad positiva. */
  direccion: [number, number, number];
  v_m_s: number[];
}

export interface SerieMarcha {
  hz: number;
  duracion_s: number;
  t: number[];
  cuerpos: Record<string, CuerpoSerie>;
  productos: ProductoSerie[];
  juntas: Record<string, { tipo: string; unidad: string; q: number[] }>;
  bandas: BandaSerie[];
  resumen: Record<string, unknown>;
  avisos: string[];
  mensaje?: string;
  firma?: string;
  escenario?: string;
  en_cache?: boolean;
}

/** Tramo de `t` que contiene `x`: el índice `i` con t[i] ≤ x < t[i+1] y la fracción entre los
 *  dos. Fuera del rango se pega al extremo (fracción 0). Búsqueda binaria: la serie de 60 s
 *  tiene 3000 muestras y se consulta en cada fotograma. */
export function tramo(t: number[], x: number): { i: number; f: number } {
  const n = t.length;
  if (n === 0 || x <= t[0]) return { i: 0, f: 0 };
  if (x >= t[n - 1]) return { i: n - 1, f: 0 };
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (t[mid] <= x) lo = mid;
    else hi = mid;
  }
  const span = t[hi] - t[lo];
  return { i: lo, f: span <= 1e-12 ? 0 : (x - t[lo]) / span };
}

const _pa = new THREE.Vector3();
const _pb = new THREE.Vector3();
const _qa = new THREE.Quaternion();
const _qb = new THREE.Quaternion();
const _uno = new THREE.Vector3(1, 1, 1);

/** Pose en la muestra `k` de un arreglo aplanado (7 por muestra), interpolada hacia `k + 1` con
 *  la fracción `f` (lerp de la posición, slerp de la rotación). */
export function poseEn(poses: number[], k: number, f: number, out: THREE.Matrix4): THREE.Matrix4 {
  const a = k * 7;
  _pa.set(poses[a], poses[a + 1], poses[a + 2]);
  _qa.set(poses[a + 3], poses[a + 4], poses[a + 5], poses[a + 6]);
  const b = a + 7;
  if (f > 0 && b + 6 < poses.length) {
    _pb.set(poses[b], poses[b + 1], poses[b + 2]);
    _qb.set(poses[b + 3], poses[b + 4], poses[b + 5], poses[b + 6]);
    _pa.lerp(_pb, f);
    _qa.slerp(_qb, f);
  }
  return out.compose(_pa, _qa, _uno);
}

/** Pose de un producto en el tramo (i, f); `false` si todavía no nació. */
export function poseProducto(p: ProductoSerie, i: number, f: number, out: THREE.Matrix4): boolean {
  if (i < p.desde) return false;
  poseEn(p.poses, i - p.desde, f, out);
  return true;
}

/** Valor interpolado de una serie escalar (la `q` de una junta, la velocidad de una banda). */
export function valorEn(v: number[], i: number, f: number): number {
  if (!v.length) return 0;
  const a = v[Math.min(i, v.length - 1)];
  const b = v[Math.min(i + 1, v.length - 1)];
  return a + (b - a) * f;
}

/** «3,2 s»: el tiempo con un decimal y coma decimal, como el resto de la interfaz. */
export function segundos(t: number): string {
  return `${t.toFixed(1).replace(".", ",")} s`;
}

/** Una frase con lo que se cargó: duración, cajas y cuántas se cayeron. */
export function resumenMarcha(s: SerieMarcha): string {
  const cajas = s.productos.length;
  const caidas = s.resumen.productos_caidos;
  const nCaidas = Array.isArray(caidas) ? caidas.length : 0;
  const partes = [`${segundos(s.duracion_s)} simulados`];
  if (cajas) partes.push(cajas === 1 ? "1 caja" : `${cajas} cajas`);
  if (nCaidas) partes.push(nCaidas === 1 ? "1 se cayó" : `${nCaidas} se cayeron`);
  return partes.join(" · ");
}
