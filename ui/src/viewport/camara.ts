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

/** Para el vuelo que SEÑALA una pieza (plan V8.5 D13): si la pieza es chica frente al modelo, la
   caja crece alrededor de su centro hasta `fraccion` de la diagonal del modelo, para que se vea
   DÓNDE está (una esquina del gabinete, no «una pared con un cilindro»). Puro: no muta `box`. */
export function cajaConContexto(box: THREE.Box3, modelo: THREE.Box3, fraccion = 0.4): THREE.Box3 {
  const caja = box.clone();
  if (box.isEmpty() || modelo.isEmpty()) return caja;
  const diag = box.getSize(new THREE.Vector3()).length();
  const minima = modelo.getSize(new THREE.Vector3()).length() * fraccion;
  if (diag >= minima) return caja;
  return caja.expandByScalar((minima - diag) / (2 * Math.sqrt(3))); // la diagonal crece √3 por lado
}

/** Vistas fijas de la barra del visor y los atajos: dirección desde el objetivo a la cámara. */
export const VIEWS: Record<string, [number, number, number]> = {
  ISO: [1, -1, 0.8],
  Frente: [0, -1, 0.0001],
  Lateral: [1, 0, 0.0001],
  Planta: [0, 0, 1],
};

/** Dónde queda la cámara (y su objetivo) al encuadrar una caja. */
export interface PoseCamara {
  posicion: THREE.Vector3;
  objetivo: THREE.Vector3;
}

/** La pose que encuadra `box` desde la cámara en `posicion` mirando a `objetivo`: mantiene la
   dirección de la vista salvo que se dé `dir`. null con la caja vacía. Puro (no mueve nada). */
export function destinoEncuadre(
  posicion: THREE.Vector3, objetivo: THREE.Vector3, box: THREE.Box3, dir?: [number, number, number],
): PoseCamara | null {
  if (box.isEmpty()) return null;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length() || 1200;
  const v = dir
    ? new THREE.Vector3(...dir).normalize().multiplyScalar(size * 1.4)
    : posicion.clone().sub(objetivo).normalize().multiplyScalar(size * 1.4);
  return { posicion: center.clone().add(v), objetivo: center };
}

/** Encuadra una caja de un salto: mantiene la dirección actual de la cámara salvo que se dé
   `dir`. El vuelo animado es `vuelo.ts` (plan V8.5, F3b-0). */
export function encuadrar(
  camera: THREE.PerspectiveCamera, controls: { target: THREE.Vector3; update: () => unknown },
  box: THREE.Box3, dir?: [number, number, number],
): void {
  const destino = destinoEncuadre(camera.position, controls.target, box, dir);
  if (!destino) return;
  camera.position.copy(destino.posicion);
  controls.target.copy(destino.objetivo);
  controls.update();
}
