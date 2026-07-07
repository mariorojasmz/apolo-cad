import * as THREE from "three";

/* Helpers PUROS de manipulación directa (Boceto · Fase 4). Sin escena/render → testeable. */

/** Intersección del rayo con el plano horizontal z = zHeight. null si es paralelo. */
export function rayPlanePoint(ray: THREE.Ray, zHeight: number): THREE.Vector3 | null {
  const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), -zHeight);
  const out = new THREE.Vector3();
  return ray.intersectPlane(plane, out) ? out : null;
}

/** Distancia con signo a lo largo del eje (P, N) del punto de acercamiento más próximo al
   rayo del cursor — arrastre de 1 eje (mínima distancia entre dos líneas cruzadas). */
export function distanceAlongAxis(P: THREE.Vector3, N: THREE.Vector3, ray: THREE.Ray): number {
  const w0 = P.clone().sub(ray.origin);
  const a = N.dot(N);
  const b = N.dot(ray.direction);
  const c = ray.direction.dot(ray.direction);
  const d = N.dot(w0);
  const e = ray.direction.dot(w0);
  const denom = a * c - b * b;
  if (Math.abs(denom) < 1e-9) return 0; // rayo paralelo al eje → sin componente
  return (b * e - c * d) / denom;
}
