import * as THREE from "three";

/* Movimientos de cámara de los botones del visor (plan modo-visor, D5) y la caja a encuadrar
   del evento `apolo:fit` (D8). Fuera de Viewport.tsx, que está congelado por el trinquete de
   tamaño. */

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

/** Piezas que pide encuadrar un `apolo:fit`: `detail.ids` (varias: «Ver» del aviso del agente)
   o `detail.id` (una: árbol, menú contextual). Vacío = encuadrar la selección o el modelo. */
export function idsDelEncuadre(detail: unknown): string[] {
  const d = (detail ?? {}) as { id?: unknown; ids?: unknown };
  if (Array.isArray(d.ids)) return d.ids.filter((x): x is string => typeof x === "string");
  return typeof d.id === "string" && d.id ? [d.id] : [];
}

/** Caja que envuelve las mallas de esos ids; las que no están (ocultas, eliminadas) se
   ignoran. null si no quedó ninguna. */
export function cajaDe(meshes: ReadonlyMap<string, THREE.Object3D>, ids: Iterable<string>): THREE.Box3 | null {
  const caja = new THREE.Box3();
  let alguna = false;
  for (const id of ids) {
    const m = meshes.get(id);
    if (m) { caja.expandByObject(m); alguna = true; }
  }
  return alguna ? caja : null;
}
