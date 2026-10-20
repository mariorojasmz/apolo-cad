import * as THREE from "three";
import type { Relieve } from "./acabados";

/* Relieves PROCEDURALES de los acabados (D5 de visor-realista): sin texturas descargadas (CSP y
   licencias). Cada tipo es un mapa de alturas de LADO px en escala de grises, generado una vez
   con una semilla fija (determinista) y compartido; cada acabado lleva su copia con la escala
   en mm (`repeat`). Las piezas no traen UV del servidor: `uvCaja` las proyecta por la cara
   dominante de cada triángulo, en mm (mapeo de caja). VTK no pinta relieves: es detalle de
   cerca, no cambia el color ni el brillo. */

export const LADO = 128;

type Generador = (x: number, y: number, ruido: Ruido) => number;

/** Ruido de valor periódico (LADO) con semilla: la textura se repite sin costura. */
export class Ruido {
  private readonly valores: Float32Array;
  constructor(semilla: number) {
    this.valores = new Float32Array(LADO * LADO);
    let s = semilla >>> 0 || 1;
    for (let i = 0; i < this.valores.length; i++) {
      s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; // xorshift32
      this.valores[i] = s / 0xffffffff;
    }
  }
  /** Valor aleatorio de la celda entera (i, j), periódico en LADO. */
  celda(i: number, j: number): number {
    const m = (n: number) => ((n % LADO) + LADO) % LADO;
    return this.valores[m(j) * LADO + m(i)];
  }
  /** Ruido suave en (x, y) con celdas de `paso` px (interpolación coseno). */
  suave(x: number, y: number, paso: number): number {
    const fx = x / paso, fy = y / paso;
    const i = Math.floor(fx), j = Math.floor(fy);
    const tx = (1 - Math.cos((fx - i) * Math.PI)) / 2, ty = (1 - Math.cos((fy - j) * Math.PI)) / 2;
    const n = LADO / paso; // celdas por período: la textura cierra sin costura
    const c = (a: number, b: number) => this.celda(((a % n) + n) % n, ((b % n) + n) % n);
    const a = c(i, j) + (c(i + 1, j) - c(i, j)) * tx;
    const b = c(i, j + 1) + (c(i + 1, j + 1) - c(i, j + 1)) * tx;
    return a + (b - a) * ty;
  }
}

/* Cada generador devuelve una altura 0..1 en el píxel (x, y). */
export const GENERADORES: Record<string, Generador> = {
  // piel de naranja de la pintura: ruido suave fino
  pintura: (x, y, r) => 0.6 * r.suave(x, y, 8) + 0.4 * r.suave(x, y, 4),
  // cepillado: rayas largas en X (cada fila su valor, apenas variado a lo largo)
  cepillado: (x, y, r) => 0.75 * r.celda(0, y) + 0.25 * r.suave(x, y, 32),
  // galvanizado: flores de zinc = celdas de valor constante con borde suave
  moteado: (x, y, r) => 0.8 * r.celda(Math.floor(x / 16), Math.floor(y / 16)) + 0.2 * r.suave(x, y, 4),
  // fundición: grano grueso en dos octavas
  fundicion: (x, y, r) => 0.55 * r.suave(x, y, 16) + 0.45 * r.suave(x, y, 4),
  // veta de madera: anillos a lo largo de X deformados por ruido
  veta: (x, y, r) => 0.5 + 0.5 * Math.sin(((y + 18 * r.suave(x, y, 32)) / LADO) * Math.PI * 2 * 6),
  // tejido de la banda: trama y urdimbre alternadas
  tejido: (x, y) => {
    const u = Math.sin((x / LADO) * Math.PI * 2 * 16), v = Math.sin((y / LADO) * Math.PI * 2 * 16);
    return 0.5 + 0.25 * (Math.floor(x / 8) % 2 === Math.floor(y / 8) % 2 ? u : v) + 0.25 * u * v;
  },
};

/** Mapa de alturas del tipo (RGBA en escala de grises, LADO × LADO). */
export function alturas(tipo: string, semilla = 1234): Uint8Array<ArrayBuffer> {
  const gen = GENERADORES[tipo];
  if (!gen) throw new Error(`Relieve sin generador: ${tipo}`);
  const ruido = new Ruido(semilla);
  const datos = new Uint8Array(LADO * LADO * 4);
  for (let y = 0; y < LADO; y++) {
    for (let x = 0; x < LADO; x++) {
      const v = Math.round(Math.min(Math.max(gen(x, y, ruido), 0), 1) * 255);
      const k = (y * LADO + x) * 4;
      datos[k] = datos[k + 1] = datos[k + 2] = v;
      datos[k + 3] = 255;
    }
  }
  return datos;
}

const BASES = new Map<string, THREE.DataTexture>();
const POR_ESCALA = new Map<string, THREE.Texture>();

/** Textura de relieve del acabado: compartida por tipo y escala (no se dispone con el
 * material: vive mientras viva la página, son pocas y chicas). */
export function texturaRelieve(relieve: Relieve): THREE.Texture | null {
  if (!(relieve.tipo in GENERADORES) || !(relieve.escala_mm > 0)) return null;
  const clave = `${relieve.tipo}|${relieve.escala_mm}`;
  let tex = POR_ESCALA.get(clave);
  if (tex) return tex;
  let base = BASES.get(relieve.tipo);
  if (!base) {
    base = new THREE.DataTexture(alturas(relieve.tipo), LADO, LADO, THREE.RGBAFormat);
    base.wrapS = base.wrapT = THREE.RepeatWrapping;
    base.magFilter = THREE.LinearFilter;
    base.minFilter = THREE.LinearMipmapLinearFilter;
    base.generateMipmaps = true;
    base.colorSpace = THREE.NoColorSpace; // es un dato (altura), no un color
    base.needsUpdate = true;
    BASES.set(relieve.tipo, base);
  }
  tex = base.clone(); // comparte la imagen; repeat propio
  tex.repeat.set(1 / relieve.escala_mm, 1 / relieve.escala_mm);
  tex.needsUpdate = true;
  POR_ESCALA.set(clave, tex);
  return tex;
}

/** UV en mm por mapeo de caja: cada triángulo se proyecta sobre el plano de su eje
 * dominante. La geometría debe venir SIN índice (como la deja `geometryFrom`). */
export function uvCaja(geometry: THREE.BufferGeometry): void {
  const pos = geometry.getAttribute("position");
  if (!pos || geometry.index) return;
  const uv = new Float32Array(pos.count * 2);
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const n = new THREE.Vector3(), e1 = new THREE.Vector3(), e2 = new THREE.Vector3();
  for (let t = 0; t + 2 < pos.count; t += 3) {
    a.fromBufferAttribute(pos, t); b.fromBufferAttribute(pos, t + 1); c.fromBufferAttribute(pos, t + 2);
    n.crossVectors(e1.subVectors(b, a), e2.subVectors(c, a));
    const ax = Math.abs(n.x), ay = Math.abs(n.y), az = Math.abs(n.z);
    for (let k = 0; k < 3; k++) {
      const p = k === 0 ? a : k === 1 ? b : c;
      const [u, v] = az >= ax && az >= ay ? [p.x, p.y] : ax >= ay ? [p.y, p.z] : [p.x, p.z];
      uv[(t + k) * 2] = u;
      uv[(t + k) * 2 + 1] = v;
    }
  }
  geometry.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
}
