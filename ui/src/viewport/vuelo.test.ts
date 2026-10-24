import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { cajaConContexto, destinoEncuadre } from "./camara";
import { opcionesDelEncuadre } from "./pedirEncuadre";
import { crearVueloCamara, poseEn, type ControlesVuelo } from "./vuelo";

/* Vuelo de cámara (plan V8.5 F3b-0): `apolo:fit` con `animar` recorre el encuadre con la curva
   suave en vez de saltar; con movimiento reducido salta; si la persona toma la cámara, se corta. */

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

function controles(): ControlesVuelo & { updates: number; disparar: () => void } {
  const oyentes: (() => void)[] = [];
  const c = {
    target: v(0, 0, 0),
    updates: 0,
    update: () => { c.updates++; },
    addEventListener: (_t: "start", fn: () => void) => { oyentes.push(fn); },
    removeEventListener: (_t: "start", fn: () => void) => { oyentes.splice(oyentes.indexOf(fn), 1); },
    disparar: () => { for (const fn of [...oyentes]) fn(); },
  };
  return c;
}

describe("destinoEncuadre", () => {
  it("centra la caja y mantiene la dirección de la vista", () => {
    const caja = new THREE.Box3(v(90, -10, -10), v(110, 10, 10));
    const d = destinoEncuadre(v(0, -1000, 0), v(0, 0, 0), caja)!;
    expect(d.objetivo.toArray()).toEqual([100, 0, 0]);
    const dir = d.posicion.clone().sub(d.objetivo).normalize();
    expect(dir.y).toBeCloseTo(-1);
    expect(d.posicion.distanceTo(d.objetivo)).toBeCloseTo(Math.sqrt(3 * 20 * 20) * 1.4);
  });
  it("con la caja vacía, nada", () => {
    expect(destinoEncuadre(v(0, -1, 0), v(0, 0, 0), new THREE.Box3())).toBeNull();
  });
});

describe("cajaConContexto", () => {
  const modelo = new THREE.Box3(v(0, 0, 0), v(500, 200, 600));
  const diag = (b: THREE.Box3) => b.getSize(new THREE.Vector3()).length();

  it("una pieza chica crece alrededor de su centro hasta ver dónde está", () => {
    const chica = new THREE.Box3(v(250, -42, 56), v(274, -18, 84));
    const c = cajaConContexto(chica, modelo);
    expect(diag(c)).toBeGreaterThan(0.38 * diag(modelo));
    expect(c.getCenter(new THREE.Vector3()).distanceTo(chica.getCenter(new THREE.Vector3()))).toBeLessThan(1e-9);
    expect(chica.max.x).toBe(274); // no muta la caja que recibe
  });

  it("una pieza grande queda igual", () => {
    const grande = new THREE.Box3(v(0, 0, 0), v(400, 100, 500));
    expect(cajaConContexto(grande, modelo).equals(grande)).toBe(true);
  });
});

describe("poseEn", () => {
  const desde = { posicion: v(0, -1000, 0), objetivo: v(0, 0, 0) };
  const hasta = { posicion: v(100, 0, 100), objetivo: v(100, 0, 0) };

  it("en los extremos es la pose de salida y la de llegada", () => {
    const a = poseEn(desde, hasta, 0), b = poseEn(desde, hasta, 1);
    expect(a.posicion.distanceTo(desde.posicion)).toBeLessThan(1e-6);
    expect(b.posicion.distanceTo(hasta.posicion)).toBeLessThan(1e-6);
    expect(b.objetivo.distanceTo(hasta.objetivo)).toBeLessThan(1e-6);
  });

  it("a mitad: el objetivo a mitad de camino y la distancia en proporción (no en línea recta)", () => {
    const m = poseEn(desde, hasta, 0.5);
    expect(m.objetivo.x).toBeCloseTo(50);
    expect(m.posicion.distanceTo(m.objetivo)).toBeCloseTo(Math.sqrt(1000 * 100)); // media geométrica
  });

  it("con la misma dirección de vista, la dirección no cambia en todo el vuelo", () => {
    const h2 = { posicion: v(100, -50, 0), objetivo: v(100, 0, 0) };
    for (const k of [0.2, 0.5, 0.8]) {
      const p = poseEn(desde, h2, k);
      const dir = p.posicion.clone().sub(p.objetivo).normalize();
      expect(dir.y).toBeCloseTo(-1);
    }
  });
});

describe("crearVueloCamara", () => {
  const destino = { posicion: v(100, -100, 0), objetivo: v(100, 0, 0) };

  it("recorre el encuadre en la duración pedida con el reloj del cuadro", () => {
    const cam = new THREE.PerspectiveCamera();
    cam.position.set(0, -1000, 0);
    const c = controles();
    const vuelo = crearVueloCamara(cam, c, () => false);
    vuelo.volar(destino, 300);
    expect(cam.position.y).toBe(-1000); // arranca en el próximo cuadro, no en el clic
    vuelo.tick(5000); // primer cuadro: t0
    expect(cam.position.y).toBeCloseTo(-1000);
    vuelo.tick(5150);
    expect(vuelo.enCurso()).toBe(true);
    expect(c.target.x).toBeGreaterThan(40); // la curva va adelantada a la mitad del tiempo
    expect(c.target.x).toBeLessThan(100);
    vuelo.tick(5300);
    expect(vuelo.enCurso()).toBe(false);
    expect(cam.position.distanceTo(destino.posicion)).toBeLessThan(1e-6);
    expect(c.target.distanceTo(destino.objetivo)).toBeLessThan(1e-6);
    const n = c.updates;
    vuelo.tick(5400); // terminado: no toca más la cámara
    expect(c.updates).toBe(n);
  });

  it("con movimiento reducido, salta", () => {
    const cam = new THREE.PerspectiveCamera();
    const c = controles();
    const vuelo = crearVueloCamara(cam, c, () => true);
    vuelo.volar(destino);
    expect(vuelo.enCurso()).toBe(false);
    expect(cam.position.distanceTo(destino.posicion)).toBeLessThan(1e-6);
  });

  it("si la persona toma la cámara, el vuelo se corta donde está", () => {
    const cam = new THREE.PerspectiveCamera();
    cam.position.set(0, -1000, 0);
    const c = controles();
    const vuelo = crearVueloCamara(cam, c, () => false);
    vuelo.volar(destino, 300);
    vuelo.tick(0);
    vuelo.tick(100);
    const donde = cam.position.clone();
    c.disparar(); // «start» de OrbitControls
    vuelo.tick(200);
    expect(vuelo.enCurso()).toBe(false);
    expect(cam.position.equals(donde)).toBe(true);
    vuelo.dispose();
  });
});

describe("opcionesDelEncuadre", () => {
  it("por defecto salta y no selecciona (lo de siempre); sólo un true explícito las prende", () => {
    const nada = { animar: false, seleccionar: false, puntos: [] };
    expect(opcionesDelEncuadre({ id: "c1" })).toEqual(nada);
    expect(opcionesDelEncuadre(undefined)).toEqual(nada);
    expect(opcionesDelEncuadre({ ids: ["a"], animar: true, seleccionar: true })).toEqual({ ...nada, animar: true, seleccionar: true });
    expect(opcionesDelEncuadre({ animar: "si", seleccionar: 1 })).toEqual(nada);
  });
  it("los puntos que el encuadre también muestra: sólo los [x, y, z] finitos (V8.5 F3b)", () => {
    const p = opcionesDelEncuadre({ puntos: [[1, 2, 3], [1, 2], [0, Number.NaN, 0], "x", [4, 5, 6]] }).puntos;
    expect(p).toEqual([[1, 2, 3], [4, 5, 6]]);
    expect(opcionesDelEncuadre({ puntos: "no" }).puntos).toEqual([]);
  });
});
