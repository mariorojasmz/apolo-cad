import * as THREE from "three";
import type { DropResult } from "../types";

/* Cajas de "producto" del drop-test físico: overlay efímero (NO son features del
   documento). Reciben sus poses por fotograma de la simulación MuJoCo y se animan
   dentro del rAF loop del viewport (sin re-render de React). */

const PRODUCT_COLOR = 0xc9a36a; // tono "cartón"
const _ONE = new THREE.Vector3(1, 1, 1);

/** Pose 4×4 FILA-MAYOR (lista de listas, mm) → THREE.Matrix4.
 *  `Matrix4.set` toma sus argumentos por FILAS, así que casa directo con la matriz
 *  del backend de física. (Ojo: `feat.matrix` de la escena es COLUMNA-mayor y usa
 *  `fromArray` — convención distinta a propósito.) */
function poseToMatrix(p: number[][], out: THREE.Matrix4): THREE.Matrix4 {
  return out.set(
    p[0][0], p[0][1], p[0][2], p[0][3],
    p[1][0], p[1][1], p[1][2], p[1][3],
    p[2][0], p[2][1], p[2][2], p[2][3],
    p[3][0], p[3][1], p[3][2], p[3][3],
  );
}

/** Una caja por producto. `BoxGeometry` está centrada en origen = origen del cuerpo
 *  MuJoCo → la pose la coloca directa (sin baseMatrix). Posa el fotograma inicial. */
export function buildProductMeshes(result: DropResult, group: THREE.Group): Map<string, THREE.Mesh> {
  const meshes = new Map<string, THREE.Mesh>();
  for (const p of result.products) {
    const geom = new THREE.BoxGeometry(p.w, p.d, p.h);
    const material = new THREE.MeshStandardMaterial({
      color: PRODUCT_COLOR,
      roughness: 0.85,
      metalness: 0.0,
      envMapIntensity: 1.0,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geom, material);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.matrixAutoUpdate = false;
    const pose0 = result.frames[0]?.poses[p.name];
    if (pose0) poseToMatrix(pose0, mesh.matrix);
    else mesh.matrix.makeTranslation(p.x, p.y, p.z);
    mesh.matrixWorldNeedsUpdate = true;
    meshes.set(p.name, mesh);
    group.add(mesh);
  }
  return meshes;
}

// temporales reutilizados (evita asignar por fotograma·producto)
const _mLo = new THREE.Matrix4();
const _mHi = new THREE.Matrix4();
const _pLo = new THREE.Vector3();
const _pHi = new THREE.Vector3();
const _qLo = new THREE.Quaternion();
const _qHi = new THREE.Quaternion();
const _scrap = new THREE.Vector3();
const _pos = new THREE.Vector3();
const _quat = new THREE.Quaternion();

/** Pose interpolada en el instante t (lerp de traslación + slerp de rotación).
 *  Interpola por `t` real (los fotogramas no caen en múltiplos exactos de 1/fps). */
export function interpolatePose(
  frames: DropResult["frames"],
  t: number,
  name: string,
  out: THREE.Matrix4,
): THREE.Matrix4 {
  const n = frames.length;
  if (n === 0) return out;
  if (n === 1 || t <= frames[0].t) {
    const p = frames[0].poses[name];
    return p ? poseToMatrix(p, out) : out;
  }
  if (t >= frames[n - 1].t) {
    const p = frames[n - 1].poses[name];
    return p ? poseToMatrix(p, out) : out;
  }
  let i = 0;
  while (i < n - 1 && frames[i + 1].t < t) i++;
  const lo = frames[i];
  const hi = frames[i + 1];
  const lp = lo.poses[name];
  const hp = hi.poses[name];
  if (!lp || !hp) return out;
  const span = hi.t - lo.t;
  const f = span <= 1e-9 ? 0 : (t - lo.t) / span;
  poseToMatrix(lp, _mLo).decompose(_pLo, _qLo, _scrap);
  poseToMatrix(hp, _mHi).decompose(_pHi, _qHi, _scrap);
  _pos.lerpVectors(_pLo, _pHi, f);
  _quat.slerpQuaternions(_qLo, _qHi, f);
  return out.compose(_pos, _quat, _ONE);
}

export interface DropAnimator {
  /** Llamar cada fotograma del rAF loop del viewport. Lee play/speed por callback. */
  tick: (nowMs: number) => void;
}

/** Reproduce la trayectoria sobre las cajas. Modo stop-and-rest: al cruzar la
 *  duración fija la pose final y llama `onEnd` UNA vez (→ setPhysicsPlaying(false)).
 *  Pausa = no acumula tiempo. Para "Repetir" se reconstruye el animador (token++). */
export function createDropAnimator(
  result: DropResult,
  meshes: Map<string, THREE.Mesh>,
  readState: () => { playing: boolean; speed: number },
  onEnd: () => void,
): DropAnimator {
  const dur = result.frames.length ? result.frames[result.frames.length - 1].t : 0;
  const animatable = dur > 0 && result.frames.length >= 2;
  let elapsed = 0;
  let last = 0;
  let done = false;

  const poseAll = (t: number) => {
    for (const [name, mesh] of meshes) {
      interpolatePose(result.frames, t, name, mesh.matrix);
      mesh.matrixWorldNeedsUpdate = true;
    }
  };

  return {
    tick: (nowMs) => {
      if (done) return;
      if (!animatable) {
        poseAll(dur);
        done = true;
        onEnd();
        return;
      }
      const { playing, speed } = readState();
      if (!playing) {
        last = nowMs;
        return;
      }
      if (!last) last = nowMs;
      elapsed += ((nowMs - last) / 1000) * Math.max(0.05, speed);
      last = nowMs;
      if (elapsed >= dur) {
        elapsed = dur;
        poseAll(dur);
        done = true;
        onEnd();
        return;
      }
      poseAll(elapsed);
    },
  };
}

export function disposeProducts(group: THREE.Group): void {
  for (const child of group.children) {
    if (child instanceof THREE.Mesh) {
      child.geometry.dispose();
      (child.material as THREE.Material).dispose();
    }
  }
  group.clear();
}
