import * as THREE from "three";
import { useStore } from "../state/store";
import type { FeatureOut, JointOut } from "../types";
import type { GizmoMode, SectionAxis } from "./BarraVista";
import type { VistaCtx } from "./interaccion/ctx";
import { soloLecturaDe } from "../state/soloLectura";

/* Planos de sección, gizmo enganchado a la selección y pose cinemática (sólo visual). Salieron
   de Viewport.tsx sin cambiar la lógica (plan piso-con-sombra, F1). */

export function sectionPlanes(axis: SectionAxis, pos: number, features: FeatureOut[]): THREE.Plane[] {
  if (!axis || features.length === 0) return [];
  const idx = axis === "x" ? 0 : axis === "y" ? 1 : 2;
  let min = Infinity;
  let max = -Infinity;
  for (const f of features) {
    if (!f.visible) continue;
    min = Math.min(min, f.bbox.min[idx]);
    max = Math.max(max, f.bbox.max[idx]);
  }
  if (!Number.isFinite(min)) return [];
  const d = min + ((max - min) * pos) / 100 + 0.01;
  const normal = new THREE.Vector3(
    axis === "x" ? -1 : 0,
    axis === "y" ? -1 : 0,
    axis === "z" ? -1 : 0,
  );
  return [new THREE.Plane(normal, d)];
}

export function attachGizmo(ctx: Pick<VistaCtx, "gizmo" | "meshes">, selection: string[], mode: GizmoMode, jointValues: Record<string, number>) {
  const posing = Object.values(jointValues).some((v) => v !== 0);
  // en sólo lectura (D4 del plan núcleo-abierto-extensiones-privadas) no hay gizmo: no se edita
  if (mode === "off" || selection.length !== 1 || posing || soloLecturaDe(useStore.getState().scene)) {
    ctx.gizmo.detach();
    return;
  }
  const mesh = ctx.meshes.get(selection[0]);
  if (!mesh) {
    ctx.gizmo.detach();
    return;
  }
  // modo escala: guarda en la malla las cotas base + el comando (create_box) → commitGizmo
  // mapea el factor de escala a width/depth/height del comando
  if (mode === "scale") {
    const st = useStore.getState();
    const feat = st.scene?.features.find((f) => f.id === selection[0]);
    const cmd = st.scene?.document.commands.find((c) => c.id === feat?.command_id);
    if (cmd?.type === "create_box") {
      mesh.userData.cmdId = cmd.id;
      mesh.userData.boxDims = {
        w: Number(cmd.params.width), d: Number(cmd.params.depth), h: Number(cmd.params.height),
      };
    }
  }
  ctx.gizmo.setMode(mode);
  ctx.gizmo.attach(mesh);
}

/* Cinemática directa (solo visual): pose(hijo) = pose(padre) · T(o) · R(eje, v) · T(-o) */
export function computePoses(joints: JointOut[], values: Record<string, number>): Map<string, THREE.Matrix4> {
  const byChild = new Map(joints.map((j) => [j.child, j]));
  const memo = new Map<string, THREE.Matrix4>();

  const poseFor = (id: string, depth = 0): THREE.Matrix4 => {
    const cached = memo.get(id);
    if (cached) return cached;
    const joint = byChild.get(id);
    let m: THREE.Matrix4;
    if (!joint || depth > 64) {
      m = new THREE.Matrix4();
    } else {
      const parent = poseFor(joint.parent, depth + 1);
      const v = values[joint.name] ?? 0;
      const local = new THREE.Matrix4();
      if (v !== 0 && joint.type !== "fija") {
        const axis = new THREE.Vector3(joint.axis[0], joint.axis[1], joint.axis[2]).normalize();
        if (joint.type === "prismatica") {
          local.makeTranslation(axis.x * v, axis.y * v, axis.z * v);
        } else {
          const [ox, oy, oz] = joint.origin;
          local
            .makeTranslation(ox, oy, oz)
            .multiply(new THREE.Matrix4().makeRotationAxis(axis, THREE.MathUtils.degToRad(v)))
            .multiply(new THREE.Matrix4().makeTranslation(-ox, -oy, -oz));
        }
      }
      m = parent.clone().multiply(local);
    }
    memo.set(id, m);
    return m;
  };

  for (const j of joints) {
    poseFor(j.parent);
    poseFor(j.child);
  }
  return memo;
}

const IDENTITY = new THREE.Matrix4();

export function applyKinematicPoses(
  meshes: Map<string, THREE.Mesh>,
  joints: JointOut[] | null,
  values: Record<string, number>,
) {
  const posing = !!joints && Object.values(values).some((v) => v !== 0);
  const poses = posing ? computePoses(joints!, values) : null;

  for (const [id, mesh] of meshes) {
    const base = mesh.userData.baseMatrix as THREE.Matrix4;
    const pose = poses?.get(id);
    if (pose && !pose.equals(IDENTITY)) {
      mesh.matrixAutoUpdate = false;
      mesh.matrix.copy(pose).multiply(base);
      mesh.matrixWorldNeedsUpdate = true;
    } else if (!mesh.matrixAutoUpdate) {
      mesh.matrixAutoUpdate = true;
      mesh.position.copy(mesh.userData.p0 as THREE.Vector3);
      mesh.quaternion.copy(mesh.userData.q0 as THREE.Quaternion);
      mesh.updateMatrix();
    }
  }
}
