import { describe, expect, it, vi } from "vitest";
import * as THREE from "three";
import type { FeatureOut, JointOut } from "../types";
import { applyKinematicPoses, attachGizmo, computePoses, sectionPlanes } from "./poses";

/* Sección, cinemática y gizmo: lo que salió puro de Viewport.tsx (plan piso-con-sombra, F1). */

const pieza = (id: string, min: number[], max: number[], visible = true) =>
  ({ id, visible, bbox: { min, max } }) as unknown as FeatureOut;

const junta = (j: Partial<JointOut>): JointOut =>
  ({ name: "j", type: "giratoria", parent: "base", child: "brazo", origin: [0, 0, 0], axis: [0, 0, 1],
     lower: -180, upper: 180, command_id: "c", ...j });

describe("sectionPlanes", () => {
  const piezas = [pieza("a", [0, 0, 0], [100, 10, 10]), pieza("b", [50, 0, 0], [200, 10, 10]), pieza("oculta", [-500, 0, 0], [900, 0, 0], false)];

  it("sin eje o sin piezas no corta", () => {
    expect(sectionPlanes("", 50, piezas)).toEqual([]);
    expect(sectionPlanes("x", 50, [])).toEqual([]);
  });

  it("corta al porcentaje del bbox de las piezas VISIBLES, mirando hacia −eje", () => {
    const [p] = sectionPlanes("x", 50, piezas);
    expect(p.normal.toArray()).toEqual([-1, 0, 0]);
    expect(p.constant).toBeCloseTo(100.01); // 0 + 200·50 % + 0.01
    expect(sectionPlanes("z", 0, piezas)[0].normal.toArray()).toEqual([0, 0, -1]);
  });
});

describe("computePoses", () => {
  it("una junta giratoria rota al hijo sobre su origen", () => {
    const poses = computePoses([junta({ origin: [100, 0, 0] })], { j: 90 });
    const p = new THREE.Vector3(200, 0, 0).applyMatrix4(poses.get("brazo")!);
    expect(p.x).toBeCloseTo(100);
    expect(p.y).toBeCloseTo(100);
    expect(poses.get("base")!.equals(new THREE.Matrix4())).toBe(true);
  });

  it("encadena: el nieto hereda la pose del hijo (prismática después de giratoria)", () => {
    const poses = computePoses(
      [junta({ origin: [0, 0, 0] }), junta({ name: "p", type: "prismatica", parent: "brazo", child: "pinza", axis: [1, 0, 0] })],
      { j: 90, p: 10 },
    );
    const p = new THREE.Vector3(0, 0, 0).applyMatrix4(poses.get("pinza")!);
    expect(p.x).toBeCloseTo(0);
    expect(p.y).toBeCloseTo(10); // el +X de la pinza quedó girado a +Y
  });

  it("una junta fija o en cero no mueve", () => {
    const poses = computePoses([junta({ type: "fija" })], { j: 45 });
    expect(poses.get("brazo")!.equals(new THREE.Matrix4())).toBe(true);
  });
});

describe("applyKinematicPoses", () => {
  const malla = (x: number) => {
    const m = new THREE.Mesh();
    m.position.set(x, 0, 0);
    m.updateMatrix();
    m.userData.baseMatrix = m.matrix.clone();
    m.userData.p0 = m.position.clone();
    m.userData.q0 = m.quaternion.clone();
    return m;
  };

  it("posa el hijo con matriz manual y lo devuelve a su sitio al volver a cero", () => {
    const brazo = malla(200);
    const meshes = new Map([["brazo", brazo], ["base", malla(0)]]);
    const juntas = [junta({ origin: [100, 0, 0] })];
    applyKinematicPoses(meshes, juntas, { j: 90 });
    expect(brazo.matrixAutoUpdate).toBe(false);
    const p = new THREE.Vector3().setFromMatrixPosition(brazo.matrix);
    expect(p.x).toBeCloseTo(100);
    expect(p.y).toBeCloseTo(100);
    expect(meshes.get("base")!.matrixAutoUpdate).toBe(true);

    applyKinematicPoses(meshes, juntas, { j: 0 });
    expect(brazo.matrixAutoUpdate).toBe(true);
    expect(brazo.position.toArray()).toEqual([200, 0, 0]);
  });
});

describe("attachGizmo", () => {
  const gizmoFalso = () => ({ detach: vi.fn(), attach: vi.fn(), setMode: vi.fn() });
  const ctx = (g: ReturnType<typeof gizmoFalso>) =>
    ({ gizmo: g, meshes: new Map([["a", new THREE.Mesh()]]) }) as unknown as Parameters<typeof attachGizmo>[0];

  it("se engancha a una sola pieza en el modo pedido", () => {
    const g = gizmoFalso();
    attachGizmo(ctx(g), ["a"], "translate", {});
    expect(g.setMode).toHaveBeenCalledWith("translate");
    expect(g.attach).toHaveBeenCalledTimes(1);
  });

  it("se suelta sin modo, con varias piezas, sin malla o con una pose cinemática", () => {
    for (const [sel, modo, valores] of [
      [["a"], "off", {}], [["a", "b"], "rotate", {}], [["zz"], "rotate", {}], [["a"], "rotate", { j: 5 }],
    ] as const) {
      const g = gizmoFalso();
      attachGizmo(ctx(g), [...sel], modo, valores);
      expect(g.detach).toHaveBeenCalled();
      expect(g.attach).not.toHaveBeenCalled();
    }
  });
});
