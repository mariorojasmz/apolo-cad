import * as THREE from "three";

/* Tiradores de caja para "estirar por las caras" (Boceto · Fase 4B). PURO: calcula
   posiciones/ejes desde el AABB mundo. Exacto para cajas ALINEADAS a ejes (el caso actual;
   las rotadas se cubren con F4C). La interacción/overlay vive en Viewport.tsx. */

export type BoxDim = "width" | "depth" | "height";

/** Una dimensión horizontal que un tirador redimensiona, con la coordenada FIJA (ancla) del
   lado opuesto sobre ese eje. */
export interface StretchAffect { dim: "width" | "depth"; i: 0 | 1; fixed: number; }

/** Tirador de estirón anclado a la BASE (TinkerCad): 4 esquinas inferiores (escalan ancho+fondo
   desde la esquina opuesta) + 4 medios de arista inferior (escalan una dimensión desde la
   arista opuesta). Todos a la altura de la base (z = min). */
export interface BaseHandle {
  kind: "corner" | "edge";
  pos: [number, number, number];
  affects: StretchAffect[]; // 2 (esquina) o 1 (arista)
}

export function baseHandles(min: number[], max: number[]): BaseHandle[] {
  const cx = (min[0] + max[0]) / 2, cy = (min[1] + max[1]) / 2, z = min[2];
  const fixX = (sx: number) => (sx === max[0] ? min[0] : max[0]);
  const fixY = (sy: number) => (sy === max[1] ? min[1] : max[1]);
  const out: BaseHandle[] = [];
  for (const sx of [min[0], max[0]]) for (const sy of [min[1], max[1]]) {
    out.push({ kind: "corner", pos: [sx, sy, z], affects: [
      { dim: "width", i: 0, fixed: fixX(sx) }, { dim: "depth", i: 1, fixed: fixY(sy) },
    ] });
  }
  for (const sx of [min[0], max[0]]) out.push({ kind: "edge", pos: [sx, cy, z], affects: [{ dim: "width", i: 0, fixed: fixX(sx) }] });
  for (const sy of [min[1], max[1]]) out.push({ kind: "edge", pos: [cx, sy, z], affects: [{ dim: "depth", i: 1, fixed: fixY(sy) }] });
  return out;
}

/** Posición del cuadrito de ALTURA: centro de la cara superior (o inferior si la cámara mira
   desde abajo). Escala el alto desde la base. */
export function heightHandlePos(min: number[], max: number[], cameraAbove: boolean): [number, number, number] {
  return [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, cameraAbove ? max[2] : min[2]];
}

/** Direcciones de cara CANDIDATAS donde se ancla cada flecha (perpendiculares a su eje de giro).
   Rojo(X)/Verde(Y) se limitan a las caras LATERALES (para elevarlas limpio al top); Azul(Z) usa las
   4 laterales (va a la base). */
export const ROT_CANDIDATES: Record<"x" | "y" | "z", [number, number, number][]> = {
  z: [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0]], // giro vertical → cualquier cara lateral
  x: [[0, 1, 0], [0, -1, 0]], // giro sobre X → caras ±Y
  y: [[1, 0, 0], [-1, 0, 0]], // giro sobre Y → caras ±X
};

/** Colocación GENÉRICA de una flecha de rotación (el "patrón azul" para cualquier eje): entre las
   caras `candidates` elige la más alineada con la DERECHA de la cámara `(rx,ry,rz)`, ancla la flecha
   en su centro empujada afuera `m` mm, y la sube/baja por el eje Z-MUNDO con `zFrac` (−1 base ·
   0 centro · +1 top). Devuelve la posición y la NORMAL `dir` de la cara elegida → el overlay orienta
   el arco relativo a esa cara. Todo cambia al orbitar. */
export function rotArrowPlacement(
  min: number[], max: number[], candidates: [number, number, number][],
  rx: number, ry: number, rz: number, m: number, zFrac: number,
): { pos: [number, number, number]; dir: [number, number, number] } {
  const c = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2];
  const half = [(max[0] - min[0]) / 2, (max[1] - min[1]) / 2, (max[2] - min[2]) / 2];
  let best = candidates[0], bestDot = -Infinity;
  for (const d of candidates) {
    const dot = d[0] * rx + d[1] * ry + d[2] * rz; // la cara que más mira a la derecha de la cámara
    if (dot > bestDot) { bestDot = dot; best = d; }
  }
  const pos: [number, number, number] = [
    c[0] + best[0] * (half[0] + m),
    c[1] + best[1] * (half[1] + m),
    c[2] + best[2] * (half[2] + m) + zFrac * half[2], // elevación por Z-mundo (top/base)
  ];
  return { pos, dir: best };
}

/** Punto del cono de elevación Z: encima de la cara superior, con un offset (mm). */
export function zLiftPoint(min: number[], max: number[], offset = 45): THREE.Vector3 {
  return new THREE.Vector3((min[0] + max[0]) / 2, (min[1] + max[1]) / 2, max[2] + offset);
}

/** ¿El AABB coincide con las dimensiones del comando? (caja sin rotar → tiradores exactos). */
export function isAxisAligned(min: number[], max: number[], w: number, d: number, h: number, tol = 1): boolean {
  return Math.abs(max[0] - min[0] - w) < tol && Math.abs(max[1] - min[1] - d) < tol && Math.abs(max[2] - min[2] - h) < tol;
}

/** Dimensiones EFECTIVAS de una create_box alineada a ejes, sanando params borrados/corruptos
   desde el AABB. Devuelve `null` si la caja NO es apta para tiradores directos:
   - alguna cota es EXPRESIÓN (`"=..."`) → pieza paramétrica, no tocar (rompería el vínculo).
   - alguna cota NUMÉRICA no coincide con su eje del bbox (±tol) → caja ROTADA/mal-etiquetada (OBB, pendiente).
   Una cota `undefined`/`null` (borrada por el bug de replace) se toma del bbox → la caja recupera
   tiradores y se AUTO-SANA en el primer estirón (el commit con merge reescribe la cota numérica). */
export function boxDimsFromBbox(
  min: number[], max: number[], params: Record<string, unknown>, tol = 1,
): [number, number, number] | null {
  const ext = [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
  const keys = ["width", "depth", "height"] as const;
  const out: [number, number, number] = [0, 0, 0];
  for (let i = 0; i < 3; i++) {
    const v = params[keys[i]];
    if (typeof v === "string") return null; // expresión → paramétrico
    if (v == null) { out[i] = ext[i]; continue; } // cota borrada → usa el bbox
    const n = Number(v);
    if (!Number.isFinite(n) || Math.abs(ext[i] - n) >= tol) return null; // no cuadra → rotada
    out[i] = n;
  }
  return out;
}

/* ---- Rotación (F4C): arcos por eje ---- */

/** Base ortonormal (u, v) estable perpendicular a `axis` (unit) — para medir ángulos sin saltos. */
export function axisBasis(axis: THREE.Vector3): { u: THREE.Vector3; v: THREE.Vector3 } {
  const ref = Math.abs(axis.z) < 0.9 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0);
  const u = new THREE.Vector3().crossVectors(ref, axis).normalize();
  const v = new THREE.Vector3().crossVectors(axis, u).normalize();
  return { u, v };
}

/** Del punto `ray ∩ plano(⟂axis por center)`: ángulo (rad) medido con la base (u,v) + su
   DISTANCIA al centro (para el snap por distancia estilo TinkerCad). null si es paralelo. */
export function anglePointOnAxis(
  center: THREE.Vector3, axis: THREE.Vector3, u: THREE.Vector3, v: THREE.Vector3, ray: THREE.Ray,
): { angle: number; dist: number } | null {
  const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(axis, center);
  const p = new THREE.Vector3();
  if (!ray.intersectPlane(plane, p)) return null;
  const d = p.sub(center);
  return { angle: Math.atan2(d.dot(v), d.dot(u)), dist: d.length() };
}

/** Paso de snap del ángulo según la distancia del cursor al centro (TinkerCad): cerca = fino,
   lejos = a escala. `free` (Shift) = sin snap. Devuelve el ángulo en GRADOS ya snapeado. */
export function snapAngleByDistance(deg: number, dist: number, radius: number, free: boolean): number {
  if (free) return deg;
  const r = dist / Math.max(radius, 1);
  const step = r >= 0.9 ? 22.5 : r >= 0.55 ? 5 : 1; // fuera del anillo 22.5° · medio 5° · dentro 1°
  return Math.round(deg / step) * step;
}

/** Diferencia de ángulo más corta a→b, envuelta en (-π, π] (para acumular sin saltos en ±180°). */
export function shortestAngleDiff(a: number, b: number): number {
  let d = b - a;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return d;
}
