import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { encuadreGiro, MARGEN } from "./encuadre";

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
});
