import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { poseEn, poseProducto, resumenMarcha, segundos, tramo, valorEn, type ProductoSerie, type SerieMarcha } from "./serie";

/* La serie de la marcha (plan visor-realista, D4): búsqueda del tramo e interpolación. */

const pq = (x: number, y: number, z: number, angZ = 0) => {
  const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), angZ);
  return [x, y, z, q.x, q.y, q.z, q.w];
};

describe("tramo", () => {
  const t = [0, 0.02, 0.04, 0.062, 0.08];

  it("encuentra el tramo por búsqueda binaria y la fracción dentro de él", () => {
    expect(tramo(t, 0.03)).toEqual({ i: 1, f: expect.closeTo(0.5, 9) });
    expect(tramo(t, 0.062)).toEqual({ i: 3, f: 0 }); // en una muestra exacta
    expect(tramo(t, 0.071).i).toBe(3);
    expect(tramo(t, 0.071).f).toBeCloseTo(0.5); // las muestras no son equiespaciadas
  });

  it("fuera del rango se pega a los extremos", () => {
    expect(tramo(t, -1)).toEqual({ i: 0, f: 0 });
    expect(tramo(t, 5)).toEqual({ i: 4, f: 0 });
    expect(tramo([], 1)).toEqual({ i: 0, f: 0 });
  });

  it("es igual a la búsqueda lineal en 3000 muestras", () => {
    const largo = Array.from({ length: 3000 }, (_, k) => k / 50);
    for (const x of [0.013, 7.77, 33.333, 59.97]) {
      const lineal = largo.findIndex((v, k) => v <= x && x < largo[k + 1]);
      expect(tramo(largo, x).i).toBe(lineal);
    }
  });
});

describe("poseEn", () => {
  const poses = [...pq(0, 0, 0), ...pq(100, 0, 0, Math.PI / 2)];

  it("interpola la posición en línea y la rotación por slerp", () => {
    const m = poseEn(poses, 0, 0.5, new THREE.Matrix4());
    const p = new THREE.Vector3();
    const q = new THREE.Quaternion();
    m.decompose(p, q, new THREE.Vector3());
    expect(p.x).toBeCloseTo(50);
    const esperado = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 4);
    expect(q.angleTo(esperado)).toBeLessThan(1e-6);
  });

  it("en la última muestra no lee más allá", () => {
    const m = poseEn(poses, 1, 0.7, new THREE.Matrix4());
    expect(new THREE.Vector3().setFromMatrixPosition(m).x).toBeCloseTo(100);
  });
});

describe("poseProducto", () => {
  const caja: ProductoSerie = { name: "p", producto: "p", dims_mm: [1, 1, 1], desde: 2, poses: [...pq(5, 0, 0), ...pq(15, 0, 0)] };

  it("no existe antes de su muestra `desde` y después se lee desplazado", () => {
    const m = new THREE.Matrix4();
    expect(poseProducto(caja, 1, 0.9, m)).toBe(false);
    expect(poseProducto(caja, 2, 0.5, m)).toBe(true);
    expect(new THREE.Vector3().setFromMatrixPosition(m).x).toBeCloseTo(10);
  });

  it("deja de existir cuando se acaban sus poses (un sumidero la retiró)", () => {
    const m = new THREE.Matrix4();
    expect(poseProducto(caja, 3, 0.5, m)).toBe(true);
    expect(new THREE.Vector3().setFromMatrixPosition(m).x).toBeCloseTo(15);
    expect(poseProducto(caja, 4, 0, m)).toBe(false);
  });
});

describe("valores y textos", () => {
  it("valorEn interpola y tolera el final", () => {
    expect(valorEn([0, 10, 20], 1, 0.25)).toBeCloseTo(12.5);
    expect(valorEn([0, 10], 1, 0.5)).toBe(10);
    expect(valorEn([], 0, 0)).toBe(0);
  });

  it("segundos con coma decimal y el resumen en una frase", () => {
    expect(segundos(12)).toBe("12,0 s");
    const serie = {
      duracion_s: 12, productos: [{}, {}, {}], resumen: { productos_caidos: ["p_a"] },
    } as unknown as SerieMarcha;
    expect(resumenMarcha(serie)).toBe("12,0 s simulados · 3 cajas · 1 se cayó");
    expect(resumenMarcha({ ...serie, productos: [], resumen: {} })).toBe("12,0 s simulados");
  });
});
