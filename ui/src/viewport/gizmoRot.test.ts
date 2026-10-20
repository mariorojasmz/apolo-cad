import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { actualizarTiradores, applyRotArrowPose, buildOverlay, type RotFollow } from "./gizmoRot";

/* Pose del gizmo de rotación y escala de los tiradores (salieron de Viewport.tsx, plan
   piso-con-sombra F1). La caja con tiradores de estirón usa texturas de <canvas>: no corre en
   node, se cubre en la verificación del navegador (F3). */

const camara = (x: number, y: number, z: number) => {
  const c = new THREE.PerspectiveCamera(50, 1, 1, 100000);
  c.up.set(0, 0, 1);
  c.position.set(x, y, z);
  c.lookAt(0, 0, 0);
  c.updateMatrixWorld();
  return c;
};

const ejeLocalZ = (o: THREE.Object3D) => new THREE.Vector3(0, 0, 1).applyQuaternion(o.quaternion);

describe("applyRotArrowPose", () => {
  const coplanarX: RotFollow = {
    min: [-100, -50, 0], max: [100, 50, 40], axis: "x", m: 38, mode: "coplanar", side: "back",
    zFrac: 1.2, inset: 1, tilt: 0,
  };

  it("coplanar «back»: se ancla en la cara ±X LEJOS de la cámara, sobre el tope", () => {
    const flecha = new THREE.Object3D();
    applyRotArrowPose(flecha, coplanarX, camara(1000, -800, 600));
    expect(flecha.position.x).toBeCloseTo(-100);
    expect(flecha.position.z).toBeCloseTo(20 + 1.2 * 20);
    applyRotArrowPose(flecha, coplanarX, camara(-1000, -800, 600));
    expect(flecha.position.x).toBeCloseTo(100);
  });

  it("el arco gira sobre su eje: el Z local de la flecha queda en el eje", () => {
    const flecha = new THREE.Object3D();
    applyRotArrowPose(flecha, coplanarX, camara(1000, -800, 600));
    expect(Math.abs(ejeLocalZ(flecha).x)).toBeCloseTo(1);
    const perpZ: RotFollow = { ...coplanarX, axis: "z", mode: "perp", zFrac: -1, candidates: [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0]] };
    applyRotArrowPose(flecha, perpZ, camara(1000, -800, 600));
    expect(Math.abs(ejeLocalZ(flecha).z)).toBeCloseTo(1);
  });
});

describe("buildOverlay", () => {
  it("una pieza que no es caja lleva sólo las 3 flechas de rotación (+ su zona de clic)", () => {
    const g = new THREE.Group();
    buildOverlay(g, { command_type: "extrude" }, [0, 0, 0], [100, 100, 100], {}, camara(1000, -800, 600));
    expect(g.children.length).toBe(6);
    expect(g.children.filter((c) => c.userData.kind === "rot").map((c) => c.userData.letter).sort()).toEqual(["x", "x", "y", "y", "z", "z"]);
  });

  it("sin pieza lo vacía", () => {
    const g = new THREE.Group();
    buildOverlay(g, { command_type: "extrude" }, [0, 0, 0], [100, 100, 100], {}, camara(1000, -800, 600));
    buildOverlay(g, undefined, [], [], {}, camara(1000, -800, 600));
    expect(g.children.length).toBe(0);
  });
});

describe("actualizarTiradores", () => {
  it("tamaño de pantalla constante: la escala crece con la distancia", () => {
    const g = new THREE.Group();
    const t = new THREE.Object3D();
    t.userData = { sizePx: 10 };
    g.add(t);
    const cam = camara(0, -1000, 0);
    actualizarTiradores(g, cam, { clientHeight: 500 }, false);
    const s1 = t.scale.x;
    expect(g.visible).toBe(true);
    expect(s1).toBeCloseTo((1000 * 2 * Math.tan(THREE.MathUtils.degToRad(25)) / 500) * 10);
    cam.position.set(0, -2000, 0);
    actualizarTiradores(g, cam, { clientHeight: 500 }, false);
    expect(t.scale.x).toBeCloseTo(2 * s1);
  });

  it("los oculta mientras se arrastra uno o si no hay tiradores", () => {
    const g = new THREE.Group();
    actualizarTiradores(g, camara(0, -1000, 0), { clientHeight: 500 }, false);
    expect(g.visible).toBe(false);
    g.add(new THREE.Object3D());
    actualizarTiradores(g, camara(0, -1000, 0), { clientHeight: 500 }, true);
    expect(g.visible).toBe(false);
  });

  it("el cuadrito de altura salta a la cara que mira la cámara", () => {
    const g = new THREE.Group();
    const h = new THREE.Object3D();
    h.userData = { kind: "height", minZ: 0, maxZ: 40 };
    g.add(h);
    actualizarTiradores(g, camara(0, -1000, 500), { clientHeight: 500 }, false);
    expect(h.position.z).toBe(40);
    actualizarTiradores(g, camara(0, -1000, -500), { clientHeight: 500 }, false);
    expect(h.position.z).toBe(0);
  });
});
