import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { ajustarRecorte, crearEncuadreDe, NEAR_MIN, recortePara } from "./recorte";

/** Separación mínima que distingue un buffer de profundidad de 24 bits a la distancia `d`. */
const resolucion = (d: number, near: number, far: number) => (d * d) / (near * 2 ** 24) * (1 - near / far);

const faja = new THREE.Sphere(new THREE.Vector3(0, 0, 500), 2200); // ~4 m de largo, 1 m de alto

describe("recorte de la cámara", () => {
  it("una banda de 3 mm sobre su cama se distingue a 6 m (antes: ~2 mm de resolución)", () => {
    const pos = new THREE.Vector3(4000, -4000, 2000);
    const d = pos.distanceTo(faja.center);
    expect(resolucion(d, 1, 100000)).toBeGreaterThan(1.5); // el near fijo de antes
    const { near, far } = recortePara(pos, faja, 0);
    expect(resolucion(d, near, far)).toBeLessThan(0.05);
  });

  it("nunca recorta la máquina ni el piso", () => {
    const pos = new THREE.Vector3(6000, 0, 300); // baja: el piso está más cerca que la máquina
    const { near, far } = recortePara(pos, faja, 0);
    expect(near).toBeLessThanOrEqual(300 / 2);
    expect(near).toBeLessThan(pos.distanceTo(faja.center) - faja.radius);
    expect(far).toBeGreaterThan(pos.distanceTo(faja.center) + faja.radius);
  });

  it("dentro de la esfera (acercada a una pieza) vuelve al recorte cercano mínimo", () => {
    const { near } = recortePara(new THREE.Vector3(200, 0, 600), faja, 0);
    expect(near).toBeLessThanOrEqual(2);
    expect(near).toBeGreaterThanOrEqual(NEAR_MIN);
  });

  it("rehace la proyección sólo cuando cambia", () => {
    const cam = new THREE.PerspectiveCamera(50, 16 / 9, 1, 100000);
    cam.position.set(4000, -4000, 2000);
    expect(ajustarRecorte(cam, faja, 0)).toBe(true);
    expect(cam.near).toBeGreaterThan(100);
    expect(ajustarRecorte(cam, faja, 0)).toBe(false);
  });

  it("la esfera sale de las mallas del grupo y el piso de su base", () => {
    const g = new THREE.Group();
    const m = new THREE.Mesh(new THREE.BoxGeometry(4000, 600, 900));
    m.position.set(0, 0, 450);
    g.add(m);
    g.updateMatrixWorld(true);
    const enc = crearEncuadreDe(g)();
    expect(enc).not.toBeNull();
    expect(enc!.pisoZ).toBeCloseTo(0);
    expect(enc!.esfera.radius).toBeGreaterThan(2000);
    expect(crearEncuadreDe(new THREE.Group())()).toBeNull();
  });
});
