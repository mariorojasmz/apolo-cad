import * as THREE from "three";
import { describe, expect, it } from "vitest";
import {
  anchoOcupado, distanciasPorAngulo, encuadreGiro, MARGEN, MARGEN_VIDEO, puntosDeMallas,
} from "./encuadre";
import { direccion } from "./planGuion";

/* El encuadre del giro: la caja entra en el cuadro de 16:9 en todo el recorrido, lo justo. */

function camara(): THREE.PerspectiveCamera {
  const c = new THREE.PerspectiveCamera(50, 16 / 9, 1, 100000);
  c.up.set(0, 0, 1);
  c.position.set(9000, -9000, 6000); // lejos, como deja el «encuadrar» del visor
  c.updateProjectionMatrix();
  return c;
}

/** Lo más que se sale una esquina de la caja (en coordenadas de pantalla) a lo largo del giro. */
function maximo(pos: THREE.Vector3, objetivo: THREE.Vector3, caja: THREE.Box3, grados: number): number {
  const c = camara();
  let peor = 0;
  for (let k = 0; k <= 36; k++) {
    const a = THREE.MathUtils.degToRad((grados * k) / 36);
    c.position.copy(pos).sub(objetivo).applyAxisAngle(new THREE.Vector3(0, 0, 1), a).add(objetivo);
    c.lookAt(objetivo);
    c.updateMatrixWorld(true);
    for (const x of [caja.min.x, caja.max.x]) for (const y of [caja.min.y, caja.max.y])
      for (const z of [caja.min.z, caja.max.z]) {
        const p = new THREE.Vector3(x, y, z).project(c);
        peor = Math.max(peor, Math.abs(p.x), Math.abs(p.y));
      }
  }
  return peor;
}

describe("encuadreGiro", () => {
  const caja = new THREE.Box3(new THREE.Vector3(0, 0, 0), new THREE.Vector3(4000, 700, 900));

  it("mira al centro de la caja desde la misma dirección y la deja entrar justa", () => {
    const c = camara();
    const r = encuadreGiro(c, new THREE.Vector3(0, 0, 0), caja, 360)!;
    expect(r.objetivo.toArray()).toEqual([2000, 350, 450]);
    const dir = r.posicion.clone().sub(r.objetivo).normalize();
    expect(dir.dot(c.position.clone().normalize())).toBeCloseTo(1, 5);
    const peor = maximo(r.posicion, r.objetivo, caja, 360);
    expect(peor).toBeLessThanOrEqual(MARGEN + 0.01); // entra en todo el giro…
    expect(peor).toBeGreaterThan(MARGEN - 0.05); // …sin aire de sobra
    expect(r.posicion.distanceTo(r.objetivo)).toBeLessThan(c.position.length());
  });

  it("un giro corto deja acercarse más que una vuelta entera", () => {
    const c = camara();
    const vuelta = encuadreGiro(c, new THREE.Vector3(), caja, 360)!;
    const poco = encuadreGiro(c, new THREE.Vector3(), caja, 10)!;
    expect(poco.posicion.distanceTo(poco.objetivo)).toBeLessThan(vuelta.posicion.distanceTo(vuelta.objetivo));
  });

  it("sin caja no toca nada", () => {
    expect(encuadreGiro(camara(), new THREE.Vector3(), new THREE.Box3(), 360)).toBeNull();
  });

  it("no hereda el near del visor (que puede valer cientos de mm)", () => {
    const c = camara();
    const normal = encuadreGiro(c, new THREE.Vector3(), caja, 360)!;
    c.near = 3000;
    c.updateProjectionMatrix();
    const conNear = encuadreGiro(c, new THREE.Vector3(), caja, 360)!;
    expect(conNear.posicion.distanceTo(normal.posicion)).toBeLessThan(1);
  });
});

/* El encuadre del guion (F3): la distancia sigue a cada ángulo, sobre los vértices de las mallas;
   ninguna pieza sale del cuadro en ningún ángulo y la cámara no da tirones. */
describe("distanciasPorAngulo", () => {
  /** Una faja larga con una pata alta en una punta y un motor salido de costado. */
  function maquina(): THREE.Mesh[] {
    const pieza = (dx: number, dy: number, dz: number, x: number, y: number, z: number) => {
      const m = new THREE.Mesh(new THREE.CylinderGeometry(dx / 2, dx / 2, dz, 24, 4).rotateX(Math.PI / 2)
        .scale(1, dy / dx, 1));
      m.position.set(x, y, z);
      return m;
    };
    return [pieza(4000, 600, 120, 0, 0, 800), pieza(80, 80, 1600, 1900, 250, 800),
      pieza(300, 300, 300, -1500, -500, 600)];
  }

  const ELEV = 22;
  const vista = (az: number, d: number, objetivo: THREE.Vector3) => {
    const c = camara();
    c.position.fromArray(direccion(az, ELEV)).multiplyScalar(d).add(objetivo);
    c.lookAt(objetivo);
    c.updateMatrixWorld(true);
    return c;
  };

  it("ninguna pieza sale del cuadro en ningún ángulo, con todos sus vértices", () => {
    const mallas = maquina();
    const puntos = puntosDeMallas(mallas, 400); // submuestreado fuerte a propósito
    const todos = puntosDeMallas(mallas, Infinity);
    expect(puntos.length).toBeLessThan(todos.length);
    const objetivo = new THREE.Box3().setFromPoints(todos).getCenter(new THREE.Vector3());
    const distancia = distanciasPorAngulo(camara(), objetivo, puntos, ELEV);
    let peor = 0;
    for (let az = -55; az <= 360 + 305; az += 1) {
      const c = vista(az, distancia(az), objetivo);
      for (const p of todos) {
        const q = p.clone().project(c);
        peor = Math.max(peor, Math.abs(q.x), Math.abs(q.y));
      }
    }
    expect(peor).toBeLessThan(1);
    expect(peor).toBeGreaterThan(MARGEN_VIDEO - 0.03); // justo, sin aire de sobra
  });

  it("se acerca de costado, se aleja de punta, sin tirones, y llena más que una sola distancia", () => {
    const mallas = maquina();
    const puntos = puntosDeMallas(mallas);
    const caja = new THREE.Box3().setFromPoints(puntos);
    const objetivo = caja.getCenter(new THREE.Vector3());
    const distancia = distanciasPorAngulo(camara(), objetivo, puntos, ELEV);
    expect(distancia(90)).toBeLessThan(distancia(0) * 0.8); // de costado (mira por Y) la larga llena
    for (let az = 0; az < 360; az += 1) {
      expect(Math.abs(distancia(az + 1) - distancia(az)) / distancia(az)).toBeLessThan(0.02);
    }
    expect(distancia(37)).toBeCloseTo(distancia(37 + 360), 6);
    const c0 = camara();
    c0.position.fromArray(direccion(90, ELEV)).multiplyScalar(1000).add(objetivo);
    const una = encuadreGiro(c0, objetivo, caja, 360)!.posicion.distanceTo(objetivo);
    const antes = anchoOcupado(vista(90, una, objetivo), puntos);
    const ahora = anchoOcupado(vista(90, distancia(90), objetivo), puntos);
    expect(ahora).toBeGreaterThan(antes * 1.3);
    expect(ahora).toBeGreaterThan(0.7);
  });
});
