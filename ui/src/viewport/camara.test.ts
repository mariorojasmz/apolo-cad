import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { ACERCAR, ALEJAR, dolly } from "./camara";

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
