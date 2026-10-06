import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { ACERCAR, ALEJAR, cajaDe, dolly, idsDelEncuadre } from "./camara";

/* Acercar / Alejar del visor: la cámara se mueve sobre la recta al objetivo, sin girar. */

describe("dolly", () => {
  const objetivo = new THREE.Vector3(100, 0, 0);

  it("acerca y aleja por el factor, sin cambiar la dirección", () => {
    const p = new THREE.Vector3(100, -1000, 0);
    dolly(p, objetivo, ACERCAR);
    expect(p.distanceTo(objetivo)).toBeCloseTo(800);
    expect(p.x).toBeCloseTo(100);
    dolly(p, objetivo, ALEJAR);
    expect(p.distanceTo(objetivo)).toBeCloseTo(1000);
    expect(p.y).toBeCloseTo(-1000);
  });

  it("no atraviesa el objetivo ni se va más allá del far", () => {
    const cerca = new THREE.Vector3(106, 0, 0);
    dolly(cerca, objetivo, 0.01);
    expect(cerca.distanceTo(objetivo)).toBeCloseTo(5);
    expect(cerca.x).toBeGreaterThan(objetivo.x);
    const lejos = new THREE.Vector3(100, 0, 49000);
    dolly(lejos, objetivo, 10);
    expect(lejos.distanceTo(objetivo)).toBeCloseTo(50000);
  });

  it("con la cámara sobre el objetivo no hace nada", () => {
    const p = objetivo.clone();
    dolly(p, objetivo, ACERCAR);
    expect(p.equals(objetivo)).toBe(true);
  });
});

/* `apolo:fit` encuadra una pieza (`detail.id`, árbol y menú) o varias (`detail.ids`, «Ver» del
   aviso del agente). */

describe("idsDelEncuadre", () => {
  it("acepta una pieza o varias", () => {
    expect(idsDelEncuadre({ id: "c1" })).toEqual(["c1"]);
    expect(idsDelEncuadre({ ids: ["c1", "c2"] })).toEqual(["c1", "c2"]);
  });

  it("sin ids válidos, vacío (encuadra la selección o el modelo)", () => {
    expect(idsDelEncuadre(undefined)).toEqual([]);
    expect(idsDelEncuadre(null)).toEqual([]);
    expect(idsDelEncuadre({})).toEqual([]);
    expect(idsDelEncuadre({ id: "" })).toEqual([]);
    expect(idsDelEncuadre({ ids: [1, "c2", null] })).toEqual(["c2"]);
  });
});

describe("cajaDe", () => {
  const caja = (x: number) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10));
    m.position.set(x, 0, 0);
    m.updateMatrixWorld();
    return m;
  };
  const mallas = new Map<string, THREE.Object3D>([["a", caja(0)], ["b", caja(100)]]);

  it("envuelve la unión de las piezas pedidas", () => {
    const c = cajaDe(mallas, ["a", "b"])!;
    expect(c.min.x).toBeCloseTo(-5);
    expect(c.max.x).toBeCloseTo(105);
  });

  it("ignora las que no están y da null si no queda ninguna", () => {
    const c = cajaDe(mallas, ["b", "eliminada"])!;
    expect(c.min.x).toBeCloseTo(95);
    expect(cajaDe(mallas, ["eliminada"])).toBeNull();
    expect(cajaDe(mallas, [])).toBeNull();
  });
});
