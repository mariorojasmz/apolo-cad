import * as THREE from "three";
import type { GravityResult } from "../types";
import { interpolatePose } from "./products";

/* Animación de la "caída por gravedad" sobre las MALLAS REALES de la escena (no cajas
   overlay): cada pieza dinámica de la simulación de estabilidad se mueve por su pose por
   fotograma. A diferencia de products.ts (que crea cajas en ctx.scene), aquí reutilizamos
   las mallas existentes de ctx.meshes y al terminar las restauramos a su sitio.

   Matemática: el cuerpo MuJoCo arranca en su COM C0 (centro de bbox) con rotación
   identidad; la pose P(t) (frames) es la transform de mundo de ese frame. La malla real
   tiene M0 = userData.baseMatrix (coloca su geometría recentrada en mundo en t=0). El
   desplazamiento rígido es  mesh.matrix(t) = P(t) · translation(-C0) · M0.
   Precalculamos  pre = translation(-C0) · M0  y por fotograma  mesh.matrix = P(t) · pre. */

const _tmp = new THREE.Matrix4();

export interface GravityAnimator {
  tick: (nowMs: number) => void;
}

export function createGravityAnimator(
  result: GravityResult,
  ctxMeshes: Map<string, THREE.Mesh>,
  readState: () => { playing: boolean; speed: number },
  onEnd: () => void,
): { animator: GravityAnimator; restore: () => void } {
  // precalcula por pieza dinámica: malla real + pre = translation(-com) · baseMatrix
  const items: { name: string; mesh: THREE.Mesh; pre: THREE.Matrix4 }[] = [];
  for (const p of result.products) {
    const mesh = ctxMeshes.get(p.id); // mapear por featureId
    const base = mesh?.userData.baseMatrix as THREE.Matrix4 | undefined;
    if (!mesh || !base) continue; // pieza oculta/ausente → se salta (no rompe)
    const [cx, cy, cz] = p.com;
    const pre = base.clone().premultiply(new THREE.Matrix4().makeTranslation(-cx, -cy, -cz));
    mesh.matrixAutoUpdate = false;
    items.push({ name: p.name, mesh, pre }); // interpola por name (clave MuJoCo)
  }

  const poseAll = (t: number) => {
    for (const it of items) {
      interpolatePose(result.frames, t, it.name, _tmp);
      it.mesh.matrix.copy(_tmp).multiply(it.pre);
      it.mesh.matrixWorldNeedsUpdate = true;
    }
  };

  const dur = result.frames.length ? result.frames[result.frames.length - 1].t : 0;
  const animatable = dur > 0 && result.frames.length >= 2;
  let elapsed = 0;
  let last = 0;
  let done = false;
  poseAll(0); // pose inicial = base (no salta en t=0)

  const animator: GravityAnimator = {
    tick: (nowMs) => {
      if (done || !items.length) return;
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

  // restaura las mallas tocadas a su pose base (igual que el reset de applyKinematicPoses)
  const restore = () => {
    for (const it of items) {
      const m = it.mesh;
      m.matrixAutoUpdate = true;
      const p0 = m.userData.p0 as THREE.Vector3 | undefined;
      const q0 = m.userData.q0 as THREE.Quaternion | undefined;
      if (p0) m.position.copy(p0);
      if (q0) m.quaternion.copy(q0);
      m.updateMatrix();
      m.matrixWorldNeedsUpdate = true;
    }
  };

  return { animator, restore };
}
