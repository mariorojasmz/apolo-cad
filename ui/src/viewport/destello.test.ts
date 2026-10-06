import { beforeEach, describe, expect, it } from "vitest";
import * as THREE from "three";
import { crearDestello, DURACION_DESTELLO_MS, intensidadDestello } from "./destello";
import { useVisor } from "../visor/estado";

/* El contorno verde de lo que cambió el agente late ~3 s y se apaga solo (plan modo-visor, D8). */

describe("intensidadDestello", () => {
  it("arranca encendido y late sin apagarse del todo", () => {
    expect(intensidadDestello(0)).toBeCloseTo(1);
    expect(intensidadDestello(500)).toBeCloseTo(0.35); // valle del primer latido
    expect(intensidadDestello(1000)).toBeCloseTo(1);
    expect(intensidadDestello(1500)).toBeGreaterThan(0);
  });

  it("se desvanece al final y vale 0 fuera de la ventana", () => {
    expect(intensidadDestello(DURACION_DESTELLO_MS - 100)).toBeLessThan(intensidadDestello(DURACION_DESTELLO_MS - 500));
    expect(intensidadDestello(DURACION_DESTELLO_MS)).toBe(0);
    expect(intensidadDestello(DURACION_DESTELLO_MS + 5000)).toBe(0);
    expect(intensidadDestello(-1)).toBe(0);
    expect(intensidadDestello(Number.NaN)).toBe(0);
  });
});

describe("crearDestello", () => {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera();
  const a = new THREE.Object3D();
  const b = new THREE.Object3D();
  const mallas = new Map<string, THREE.Object3D>([["a", a], ["b", b]]);

  beforeEach(() => {
    useVisor.setState({ marcados: [], pulso: 0 });
  });

  it("mientras late, contornea las mallas marcadas que existen", () => {
    const d = crearDestello(scene, camera);
    useVisor.setState({ marcados: ["a", "ya-no-esta"], pulso: 10_000 });
    d.actualizar(mallas, 10_000);
    expect(d.pass.enabled).toBe(true);
    expect(d.pass.selectedObjects).toEqual([a]);
    expect(d.pass.edgeStrength).toBeGreaterThan(0);
    d.dispose();
  });

  it("pasados los ~3 s se apaga y suelta las mallas", () => {
    const d = crearDestello(scene, camera);
    useVisor.setState({ marcados: ["a", "b"], pulso: 10_000 });
    d.actualizar(mallas, 10_000 + DURACION_DESTELLO_MS + 1);
    expect(d.pass.enabled).toBe(false);
    expect(d.pass.selectedObjects).toEqual([]);
    d.dispose();
  });

  it("sin piezas marcadas, apagado", () => {
    const d = crearDestello(scene, camera);
    d.actualizar(mallas, 0);
    expect(d.pass.enabled).toBe(false);
    d.dispose();
  });
});
