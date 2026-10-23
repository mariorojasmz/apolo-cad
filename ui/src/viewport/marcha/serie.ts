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
  /** Pose ABSOLUTA del centro de la caja desde `desde`. 7 números por muestra; se acaba antes
   *  que la serie si un sumidero la retiró (la máquina siguiente se la lleva). */
  poses: number[];
}

export interface BandaSerie {
  pieza: string;
  junta: string;
  radio_mm: number;
  /** Hacia dónde avanza la cara superior con velocidad positiva. */
  direccion: [number, number, number];
  v_m_s: number[];
  /** Recorrido acumulado (mm) por muestra. Lo trae la serie VIVA (crece con ella y se recorta
   *  igual); sin él, la faja lo integra de `v_m_s` al armarse. */
  s_mm?: number[];
}

/** Una cadena que avanza (F3, D6): sus rodillos en el marco del lazo y la junta que la mueve.
 *  Avance en pasos = signo · (q(t) − q(0)) / 360 · z. Ver `library/marcha_visual.py`. */
export interface CadenaSerie {
  pieza: string;
  junta: string;
  lado: "a" | "b";
  z: number;
  signo: number;
  /** Piñones que la física no hace girar (el del motor sin junta): giran con la cadena,
   *  2π·avance/z sobre el Z del lazo por su eje (A en el origen del lazo, B en `centro_b`). */
  pinones_libres?: { pieza: string; lado: "a" | "b"; z: number }[];
  /** Marco del lazo → mundo, 4×4 por FILAS. */
  marco: number[];
  paso: number;
  za: number;
  zb: number;
  centro_b: [number, number];
  /** Centros de los rodillos (x, y) aplanados, antihorario sobre +Z del lazo. */
  puntos: number[];
  /** [primero, cuántos] de los rodillos sentados en el piñón A / B. */
  asentados_a: [number, number];
  asentados_b: [number, number];
  rodillo_d: number;
  perno_d: number;
  alto_placa: number;
  espesor_placa: number;
  /** Tramos (z0, z1) de cada capa en el marco del lazo. */
  capas: { rodillos: [number, number][]; interiores: [number, number][]; exteriores: [number, number][]; perno: [number, number] };
}

/** Un tambor o rodillo que la banda hace girar sin que lo mueva la física (cola, retorno). */
export interface RodilloFaja {
  pieza: string;
  centro: [number, number, number];
  /** Eje de giro: ángulo = recorrido antihorario de la banda / radio. */
  eje: [number, number, number];
  radio_mm: number;
}

/** La banda con su forma real (F3, D6). La ruta es la línea media en el plano de la faja
 *  (u, w), antihoraria; recorrido antihorario por segundo = signo · v de su banda. */
export interface FajaSerie {
  pieza: string;
  junta: string;
  marco: { origen: number[]; u: number[]; w: number[]; v: number[] };
  ruta: number[];
  espesor: number;
  ancho: number;
  v_centro: number;
  largo_mm: number;
  signo: number;
  tramos: { largo_mm: number; comba_mm: number; limita: string }[];
  envueltos: string[];
  apoyos: string[];
  tension: Record<string, number | null>;
  rodillos: RodilloFaja[];
}

export interface SerieMarcha {
  hz: number;
  duracion_s: number;
  t: number[];
  cuerpos: Record<string, CuerpoSerie>;
  productos: ProductoSerie[];
  /** `q0`: la q de la PRIMERA muestra cuando la serie viva ya recortó su comienzo (la cadena
   *  avanza desde ahí). */
  juntas: Record<string, { tipo: string; unidad: string; q: number[]; q0?: number }>;
  bandas: BandaSerie[];
  /** F3: ausentes en una serie de antes (la faja y las cadenas quedan rígidas). */
  cadenas?: CadenaSerie[];
  fajas?: FajaSerie[];
  resumen: Record<string, unknown>;
  avisos: string[];
  mensaje?: string;
  firma?: string;
  escenario?: string;
  en_cache?: boolean;
  /** Serie de la máquina viva (plan V8.4): llega fotograma a fotograma por el WebSocket y
   *  crece en un anillo (`vivo/serieViva.ts`); el reproductor sigue su última muestra. */
  vivo?: boolean;
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
const _qd = new THREE.Quaternion();
const _qf = new THREE.Quaternion();
const _u = new THREE.Vector3();
const _t = new THREE.Vector3();
const _c = new THREE.Vector3();
const _v = new THREE.Vector3();

/** Pose en la muestra `k` de un arreglo aplanado (7 por muestra), interpolada hacia `k + 1` con
 *  la fracción `f` como movimiento RÍGIDO (por tornillo): gira `f·θ` alrededor del eje real del
 *  tramo y avanza `f` de lo que corre a lo largo de él. Un lerp de la posición con slerp de la
 *  rotación NO es rígido: un cuerpo que gira sobre un eje lejos del origen (las poses son
 *  T = P(t)·P(0)⁻¹, con la traslación c − R·c) se salía de su eje a mitad de cada muestra
 *  (el eje motriz de la faja, a x ≈ 3,8 m, ~15 mm por fotograma en la sesión viva). */
export function poseEn(poses: number[], k: number, f: number, out: THREE.Matrix4): THREE.Matrix4 {
  const a = k * 7;
  _pa.set(poses[a], poses[a + 1], poses[a + 2]);
  _qa.set(poses[a + 3], poses[a + 4], poses[a + 5], poses[a + 6]);
  const b = a + 7;
  if (f > 0 && b + 6 < poses.length && !Number.isNaN(poses[b])) {
    _pb.set(poses[b], poses[b + 1], poses[b + 2]);
    _qb.set(poses[b + 3], poses[b + 4], poses[b + 5], poses[b + 6]);
    interpolarRigido(f);
  }
  return out.compose(_pa, _qa, _uno);
}

/** Deja en `_pa`/`_qa` la pose rígida a la fracción `f` entre A (`_pa`, `_qa`) y B (`_pb`, `_qb`).
 *  W = B·A⁻¹ (en el mundo) es un tornillo: rotación θ sobre el eje `u` que pasa por `c` más un
 *  avance a lo largo de `u`; W(f) gira f·θ sobre ese mismo eje y avanza f. Pose = W(f)·A. */
function interpolarRigido(f: number): void {
  _qd.copy(_qb).multiply(_qf.copy(_qa).invert());
  if (_qd.w < 0) _qd.set(-_qd.x, -_qd.y, -_qd.z, -_qd.w); // el camino corto (θ ≤ 180°)
  _t.copy(_pa).applyQuaternion(_qd).negate().add(_pb); // traslación de W
  const s = Math.hypot(_qd.x, _qd.y, _qd.z);
  const theta = 2 * Math.atan2(s, _qd.w);
  if (theta < 1e-9) {
    _pa.lerp(_pb, f);
    _qa.slerp(_qb, f);
    return;
  }
  _u.set(_qd.x / s, _qd.y / s, _qd.z / s);
  const avance = _t.dot(_u);
  _t.addScaledVector(_u, -avance); // la parte perpendicular al eje
  // Punto del eje (⟂ u): c = ½·(t⊥ + cot(θ/2)·(u × t⊥)).
  _c.crossVectors(_u, _t).multiplyScalar(1 / Math.tan(theta / 2)).add(_t).multiplyScalar(0.5);
  _qf.setFromAxisAngle(_u, f * theta);
  // p(f) = R(fθ)·(pA − c) + c + f·avance·u
  _v.copy(_pa).sub(_c).applyQuaternion(_qf).add(_c).addScaledVector(_u, f * avance);
  _pa.copy(_v);
  _qa.premultiply(_qf);
}

/** Pose de un producto en el tramo (i, f); `false` si todavía no nació o ya se retiró (en la
 *  serie viva, NaN: la caja no está en el mundo). */
export function poseProducto(p: ProductoSerie, i: number, f: number, out: THREE.Matrix4): boolean {
  if (i < p.desde || (i - p.desde) * 7 >= p.poses.length) return false;
  if (Number.isNaN(p.poses[(i - p.desde) * 7])) return false;
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
