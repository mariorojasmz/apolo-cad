import * as THREE from "three";

/* Planos de recorte de la cámara ajustados a la máquina en cada cuadro.

   Con `near` fijo en 1 mm y `far` en 100 m, el buffer de profundidad de 24 bits separa a ~6 m
   sólo lo que dista más de ~2 mm (Δz ≈ d² / (near · 2²⁴)): una banda de 3–4 mm sobre su cama
   parpadeaba en manchas grises al girar (z-fighting), sobre todo en el video, que aleja la
   cámara para encuadrar la máquina entera. Con `near` a la mitad de la distancia a lo más
   cercano (la esfera de la máquina o el piso) la precisión a esa distancia baja a milésimas de
   milímetro. */

/** Recorte cercano mínimo (mm) y su fracción de la distancia cuando la cámara está DENTRO de
   la esfera de la máquina (acercada a una pieza): nada más cerca que eso queda recortado. */
export const NEAR_MIN = 1;
const NEAR_FRAC_DENTRO = 0.002;
/** El piso de estudio y la grilla se extienden más allá de la máquina: el `far` los cubre. */
const MARGEN_FAR = 4000;

export interface Recorte { near: number; far: number }

/**
 * `near`/`far` para una cámara en `pos` que mira una máquina dentro de `esfera`, con el piso en
 * `pisoZ`. `near` = la mitad de la distancia a lo más cercano (la superficie de la esfera o el
 * plano del piso): nunca recorta nada visible. `far` = el otro lado de la esfera + el piso.
 */
export function recortePara(pos: THREE.Vector3, esfera: THREE.Sphere, pisoZ: number): Recorte {
  const d = pos.distanceTo(esfera.center);
  const r = Math.max(esfera.radius, 1);
  const alPiso = Math.abs(pos.z - pisoZ);
  const aLaMaquina = d - r;
  let near: number;
  if (aLaMaquina <= 0) {
    near = Math.max(NEAR_MIN, d * NEAR_FRAC_DENTRO);
  } else {
    near = Math.max(NEAR_MIN, 0.5 * Math.min(aLaMaquina, alPiso > 0 ? alPiso : aLaMaquina));
  }
  const far = Math.max(near * 10, d + r + MARGEN_FAR + 2 * r);
  return { near, far };
}

/**
 * Ajusta la cámara a `recortePara` y rehace su proyección sólo si cambió más de un 1 %: los
 * passes (GTAO, contorno) leen `near`/`far` en cada render, así que no hay nada más que avisar.
 */
export function ajustarRecorte(cam: THREE.PerspectiveCamera, esfera: THREE.Sphere, pisoZ: number): boolean {
  const { near, far } = recortePara(cam.position, esfera, pisoZ);
  const cambio = Math.abs(near - cam.near) > 0.01 * cam.near || Math.abs(far - cam.far) > 0.01 * cam.far;
  if (!cambio) return false;
  cam.near = near;
  cam.far = far;
  cam.updateProjectionMatrix();
  return true;
}

/** La máquina que la cámara tiene que ver: su esfera envolvente y la cota del piso (su base). */
export interface Encuadre { esfera: THREE.Sphere; pisoZ: number }

/**
 * La esfera de la máquina y su piso, recalculados cada `cada` cuadros (recorrer cientos de
 * mallas por cuadro no hace falta: la marcha mueve piezas dentro de la misma caja). Sin mallas,
 * null.
 */
export function crearEncuadreDe(grupo: THREE.Object3D, cada = 20): () => Encuadre | null {
  let cuenta = 0;
  let enc: Encuadre | null = null;
  const caja = new THREE.Box3();
  return () => {
    if (enc === null || cuenta++ % cada === 0) {
      caja.makeEmpty();
      caja.expandByObject(grupo);
      enc = caja.isEmpty() ? null : { esfera: caja.getBoundingSphere(new THREE.Sphere()), pisoZ: caja.min.z };
    }
    return enc;
  };
}
