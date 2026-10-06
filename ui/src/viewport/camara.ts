import * as THREE from "three";

/* Movimientos de cámara de los botones del visor (plan modo-visor, D5). Fuera de
   Viewport.tsx, que está congelado por el trinquete de tamaño. */

/** Factores de los botones Acercar / Alejar (la rueda del mouse sigue siendo OrbitControls). */
export const ACERCAR = 0.8;
export const ALEJAR = 1.25;

/** Distancia mínima y máxima al objetivo (mm): dentro del `near`/`far` de la cámara. */
const MIN_DIST = 5;
const MAX_DIST = 50000;

/** Dolly: acerca (`factor` < 1) o aleja (> 1) `posicion` sobre la recta hacia `objetivo`,
   sin cambiar la dirección de la vista. Muta `posicion`; quien llama hace `controls.update()`. */
export function dolly(posicion: THREE.Vector3, objetivo: THREE.Vector3, factor: number): void {
  const off = posicion.clone().sub(objetivo);
  const d = off.length();
  if (!(d > 1e-6) || !(factor > 0)) return;
  const nueva = THREE.MathUtils.clamp(d * factor, MIN_DIST, MAX_DIST);
  posicion.copy(objetivo).addScaledVector(off.divideScalar(d), nueva);
}
