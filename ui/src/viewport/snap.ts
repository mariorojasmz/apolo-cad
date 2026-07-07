import * as THREE from "three";
import type { FeatureOut } from "../types";

/* Motor de snapping para el gizmo (Boceto de masas · Fase 2). Funciones PURAS: dado el
   AABB mundo de cada sólido (`feat.bbox`, que ya viaja en el scene_payload) construye un
   índice de puntos clave y encuentra el más cercano en pantalla al arrastrar. No toca
   three.js escena/render — solo matemática de proyección, así se puede testear aislado. */

export type SnapKind = "esquina" | "arista" | "cara" | "centro";

export interface SnapPoint {
  featureId: string;
  name: string;
  kind: SnapKind;
  world: THREE.Vector3;
}

export interface SnapHit {
  target: SnapPoint;
  movingIndex: number; // qué punto móvil del arrastrado casó
  correction: THREE.Vector3; // sumar a mesh.position para pegar
  px: number; // distancia en píxeles (para desempatar)
}

/** 27 puntos clave de un AABB: 8 esquinas + 12 medios de arista + 6 centros de cara + 1
   centro. El `kind` sale de cuántas coordenadas caen en el punto MEDIO (0→esquina,
   1→arista, 2→cara, 3→centro). */
export function keyPointsOfAABB(
  min: number[],
  max: number[],
): { kind: SnapKind; p: [number, number, number] }[] {
  const xs = [min[0], (min[0] + max[0]) / 2, max[0]];
  const ys = [min[1], (min[1] + max[1]) / 2, max[1]];
  const zs = [min[2], (min[2] + max[2]) / 2, max[2]];
  const out: { kind: SnapKind; p: [number, number, number] }[] = [];
  for (let i = 0; i < 3; i++)
    for (let j = 0; j < 3; j++)
      for (let k = 0; k < 3; k++) {
        const mids = (i === 1 ? 1 : 0) + (j === 1 ? 1 : 0) + (k === 1 ? 1 : 0);
        const kind: SnapKind =
          mids === 0 ? "esquina" : mids === 1 ? "arista" : mids === 2 ? "cara" : "centro";
        out.push({ kind, p: [xs[i], ys[j], zs[k]] });
      }
  return out;
}

/** Índice de todos los puntos clave de los sólidos VISIBLES, menos el que se arrastra. */
export function buildSnapIndex(features: FeatureOut[], excludeId: string | null): SnapPoint[] {
  const pts: SnapPoint[] = [];
  for (const f of features) {
    if (!f.visible || f.id === excludeId) continue;
    for (const { kind, p } of keyPointsOfAABB(f.bbox.min, f.bbox.max))
      pts.push({ featureId: f.id, name: f.name, kind, world: new THREE.Vector3(p[0], p[1], p[2]) });
  }
  return pts;
}

/** Puntos "móviles" del sólido arrastrado (8 esquinas + centro) como OFFSETS respecto a
   `startPos` (la posición de la malla al empezar el arrastre): así el mundo de cada punto
   es `mesh.position + offset` en cualquier instante, sin importar dónde esté el origen. */
export function movingOffsets(
  bbox: { min: number[]; max: number[] },
  startPos: THREE.Vector3,
): THREE.Vector3[] {
  return keyPointsOfAABB(bbox.min, bbox.max)
    .filter((k) => k.kind === "esquina" || k.kind === "centro")
    .map((k) => new THREE.Vector3(k.p[0], k.p[1], k.p[2]).sub(startPos));
}

const _v = new THREE.Vector3();

function toScreen(world: THREE.Vector3, camera: THREE.Camera, rect: DOMRect): [number, number] | null {
  _v.copy(world).project(camera);
  if (_v.z < -1 || _v.z > 1) return null; // detrás de la cámara / fuera del frustum
  return [rect.left + ((_v.x + 1) / 2) * rect.width, rect.top + ((1 - _v.y) / 2) * rect.height];
}

/** Mejor par (punto-móvil, punto-índice) cuya distancia en PÍXELES < umbral (zoom-
   independiente). Devuelve el vector de corrección a sumar a `mesh.position`, o null. */
export function nearestScreenSnap(
  movingWorld: THREE.Vector3[],
  index: SnapPoint[],
  camera: THREE.Camera,
  rect: DOMRect,
  pxThreshold: number,
): SnapHit | null {
  const movingScreen = movingWorld.map((w) => toScreen(w, camera, rect));
  let best: SnapHit | null = null;
  let bestPx = pxThreshold;
  for (const sp of index) {
    const s = toScreen(sp.world, camera, rect);
    if (!s) continue;
    for (let m = 0; m < movingWorld.length; m++) {
      const ms = movingScreen[m];
      if (!ms) continue;
      const dpx = Math.hypot(s[0] - ms[0], s[1] - ms[1]);
      if (dpx < bestPx) {
        bestPx = dpx;
        best = { target: sp, movingIndex: m, correction: sp.world.clone().sub(movingWorld[m]), px: dpx };
      }
    }
  }
  return best;
}
