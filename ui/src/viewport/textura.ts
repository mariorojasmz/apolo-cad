import * as THREE from "three";
import type { Textura } from "./acabados";
import { LADO, Ruido } from "./relieve";

/* Texturas PROCEDURALES de color y brillo de los acabados (video-realista D2): las piezas lisas
   son lo que más delata un render. Se generan en el navegador desde los parámetros de la tabla
   (`library/apariencia.py` → `acabados.json`), sin imágenes en el repo (CSP y licencias), con
   semilla fija (deterministas) y se comparten por acabado.

   - `map` multiplica el albedo: valores en [1 − variación, 1]; el color del material se
     compensa por el promedio del mapa, así el tono medio sigue siendo el de la tabla.
   - `roughnessMap` (canal G) multiplica la rugosidad, con la misma compensación.
   - En el cepillado, `anisotropy` (MeshPhysicalMaterial) estira el reflejo a lo largo de U, que
     es la dirección de las rayas del mapa (las UV de caja en mm de `relieve.ts::uvCaja`).

   VTK no las lee: el render del servidor sigue con color, rugosidad y metal (`apariencia()`). */

type Patron = (x: number, y: number, r: Ruido) => number;

/** Lentejuelas del galvanizado: celdas de Voronoi (cristales de zinc) de tono y brillo propios. */
function cristal(x: number, y: number, r: Ruido, sal: number): number {
  const paso = 16, n = LADO / paso;
  const ci = Math.floor(x / paso), cj = Math.floor(y / paso);
  let mejor = Infinity, id = 0;
  for (let dj = -1; dj <= 1; dj++) {
    for (let di = -1; di <= 1; di++) {
      const i = ci + di, j = cj + dj;
      const wi = ((i % n) + n) % n, wj = ((j % n) + n) % n; // período LADO: sin costura
      const sx = (i + r.celda(wi * 3, wj * 3 + 1)) * paso, sy = (j + r.celda(wi * 3 + 2, wj * 3)) * paso;
      const d = (sx - x) ** 2 + (sy - y) ** 2;
      if (d < mejor) { mejor = d; id = wj * n + wi; }
    }
  }
  return r.celda(id + sal, id * 7 + sal);
}

/** Por tipo: el patrón del color y el del brillo (0..1). */
export const GENERADORES_TEXTURA: Record<string, { color: Patron; rugosidad: Patron }> = {
  lentejuelas: {
    color: (x, y, r) => 0.85 * cristal(x, y, r, 0) + 0.15 * r.suave(x, y, 4),
    rugosidad: (x, y, r) => 0.8 * cristal(x, y, r, 37) + 0.2 * r.suave(x, y, 8),
  },
  // rayas finas a lo largo de X (= U): cada fila su valor, apenas variado a lo largo
  cepillado: {
    color: (x, y, r) => 0.7 * r.celda(5, y) + 0.3 * r.celda(Math.floor(x / 32), y),
    rugosidad: (x, y, r) => 0.6 * r.celda(11, y) + 0.4 * r.suave(x, y, 16),
  },
  // grano fino de la goma o del hierro: ruido de píxel más una octava suave
  grano: {
    color: (x, y, r) => 0.6 * r.celda(x, y) + 0.4 * r.suave(x, y, 4),
    rugosidad: (x, y, r) => 0.5 * r.celda(x + 64, y + 32) + 0.5 * r.suave(x, y, 4),
  },
  // piel de naranja: ondulación suave, sobre todo en el brillo
  piel_naranja: {
    color: (x, y, r) => r.suave(x, y, 16),
    rugosidad: (x, y, r) => 0.6 * r.suave(x + 40, y, 8) + 0.4 * r.suave(x, y + 40, 4),
  },
};

export interface MapaTextura {
  /** RGBA de LADO × LADO con el factor en R, G y B (0..255). */
  datos: Uint8Array<ArrayBuffer>;
  /** Promedio del factor (0..1): el material se compensa por 1 / promedio. */
  promedio: number;
}

/** Mapa del patrón con `variacion` (0..1): factor = 1 − variacion · (1 − patrón). */
export function mapaTextura(patron: Patron, variacion: number, semilla = 4321): MapaTextura {
  const ruido = new Ruido(semilla);
  const datos = new Uint8Array(LADO * LADO * 4);
  let suma = 0;
  for (let y = 0; y < LADO; y++) {
    for (let x = 0; x < LADO; x++) {
      const p = Math.min(Math.max(patron(x, y, ruido), 0), 1);
      const v = Math.round((1 - variacion * (1 - p)) * 255);
      const k = (y * LADO + x) * 4;
      datos[k] = datos[k + 1] = datos[k + 2] = v;
      datos[k + 3] = 255;
      suma += v / 255;
    }
  }
  return { datos, promedio: suma / (LADO * LADO) };
}

interface Mapas { color: THREE.Texture | null; rugosidad: THREE.Texture | null; compensaColor: number; compensaRugosidad: number }
const CACHE = new Map<string, Mapas>();

function textura(m: MapaTextura, escalaMm: number): THREE.DataTexture {
  const tex = new THREE.DataTexture(m.datos, LADO, LADO, THREE.RGBAFormat);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.generateMipmaps = true;
  tex.colorSpace = THREE.NoColorSpace; // factor lineal, no un color
  tex.repeat.set(1 / escalaMm, 1 / escalaMm); // UV en mm (uvCaja)
  tex.needsUpdate = true;
  return tex;
}

/** Mapas del acabado, compartidos por (tipo, escala, variaciones): viven mientras viva la
 * página (no se disponen con el material: son pocos y chicos). */
export function mapasTextura(t: Textura): Mapas | null {
  const gen = GENERADORES_TEXTURA[t.tipo];
  if (!gen || !(t.escala_mm > 0)) return null;
  const clave = `${t.tipo}|${t.escala_mm}|${t.variacion_color}|${t.variacion_rugosidad}`;
  let m = CACHE.get(clave);
  if (m) return m;
  const c = t.variacion_color > 0 ? mapaTextura(gen.color, t.variacion_color) : null;
  const r = t.variacion_rugosidad > 0 ? mapaTextura(gen.rugosidad, t.variacion_rugosidad, 8765) : null;
  m = {
    color: c && textura(c, t.escala_mm),
    rugosidad: r && textura(r, t.escala_mm),
    compensaColor: c ? 1 / c.promedio : 1,
    compensaRugosidad: r ? 1 / r.promedio : 1,
  };
  CACHE.set(clave, m);
  return m;
}

/** ¿El acabado necesita MeshPhysicalMaterial? (la anisotropía no existe en el Standard). */
export function pideFisico(t: Textura | null): boolean {
  return !!t && t.anisotropia > 0;
}

/** Aplica la textura al material ya armado con el color y la rugosidad de la tabla. */
export function aplicarTextura(mat: THREE.MeshStandardMaterial, t: Textura): void {
  const m = mapasTextura(t);
  if (!m) return;
  if (m.color) {
    mat.map = m.color;
    mat.color.multiplyScalar(m.compensaColor); // el tono medio queda en el albedo de la tabla
  }
  if (m.rugosidad) {
    mat.roughnessMap = m.rugosidad;
    mat.roughness = Math.min(1, mat.roughness * m.compensaRugosidad);
  }
  if (t.anisotropia > 0 && mat instanceof THREE.MeshPhysicalMaterial) {
    mat.anisotropy = t.anisotropia;
    mat.anisotropyRotation = 0; // a lo largo de U: la dirección de las rayas
  }
}
