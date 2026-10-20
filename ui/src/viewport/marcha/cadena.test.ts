import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { avanceCadena, crearCadenas, posicionEnLazo, type Punto2 } from "./cadena";
import type { CadenaSerie, SerieMarcha } from "./serie";

/* Cadenas que avanzan (plan visor-realista F3, D6) sobre un lazo de juguete: dos piñones de 6
   dientes (radio primitivo = paso) a 30 mm, 12 rodillos: 4 sentados en A, 2 en el tramo de abajo,
   4 sentados en B y 2 arriba, antihorario como los manda el servidor. */

const R = 10;
const g = (a: number) => (a * Math.PI) / 180;
function lazo(): number[] {
  const pts: number[] = [];
  for (const a of [90, 150, 210, 270]) pts.push(R * Math.cos(g(a)), R * Math.sin(g(a)));
  pts.push(10, -10, 20, -10);
  for (const a of [270, 330, 30, 90]) pts.push(30 + R * Math.cos(g(a)), R * Math.sin(g(a)));
  pts.push(20, 10, 10, 10);
  return pts;
}

function cadena(extra: Partial<CadenaSerie> = {}): CadenaSerie {
  return {
    pieza: "c1", junta: "j", lado: "a", z: 6, signo: 1,
    marco: [1, 0, 0, 100, 0, 1, 0, 0, 0, 0, 1, 50, 0, 0, 0, 1],
    paso: 10, za: 6, zb: 6, centro_b: [30, 0], puntos: lazo(),
    asentados_a: [0, 4], asentados_b: [6, 4],
    rodillo_d: 6, perno_d: 3, alto_placa: 8, espesor_placa: 1,
    capas: { rodillos: [[-2, 2]], interiores: [[-3, -2], [2, 3]], exteriores: [[-4.1, -3.1], [3.1, 4.1]], perno: [-5, 5] },
    ...extra,
  };
}

function serie(cadenas: CadenaSerie[], q = [0, 60, 120]): SerieMarcha {
  return {
    hz: 1, duracion_s: 2, t: [0, 1, 2], cuerpos: {}, productos: [], bandas: [], resumen: {}, avisos: [],
    juntas: { j: { tipo: "continua", unidad: "grados", q } }, cadenas,
  };
}

const p = (): Punto2 => ({ x: 0, y: 0 });

describe("posicionEnLazo", () => {
  it("en un paso entero cada rodillo cae en un rodillo del CAD (y el lazo cierra)", () => {
    const c = cadena();
    for (let k = 0; k < 12; k++) {
      const a = posicionEnLazo(c, k, p()), b = posicionEnLazo(c, k + 12, p());
      expect([a.x, a.y]).toEqual([c.puntos[2 * k], c.puntos[2 * k + 1]]);
      expect(b.x).toBeCloseTo(a.x);
      expect(b.y).toBeCloseTo(a.y);
    }
  });

  it("entre dos rodillos sentados va por el círculo del piñón, no por la cuerda", () => {
    const c = cadena();
    const a = posicionEnLazo(c, 0.5, p()); // entre 90° y 150° de A
    expect(Math.hypot(a.x, a.y)).toBeCloseTo(R);
    expect(Math.atan2(a.y, a.x)).toBeCloseTo(g(120));
    const b = posicionEnLazo(c, 7.5, p()); // en B, entre 330° y 30°
    expect(Math.hypot(b.x - 30, b.y)).toBeCloseTo(R);
    expect(b.y).toBeCloseTo(0);
  });

  it("en el tramo recto va en recta", () => {
    const m = posicionEnLazo(cadena(), 4.5, p());
    expect([m.x, m.y]).toEqual([15, -10]);
  });
});

describe("avanceCadena", () => {
  it("un diente del piñón motriz corre un eslabón, con el signo del eje", () => {
    const s = serie([cadena()]);
    expect(avanceCadena(cadena(), s, 1, 0)).toBeCloseTo(1); // 60° de un piñón de 6 dientes
    expect(avanceCadena(cadena(), s, 1, 0.5)).toBeCloseTo(1.5);
    expect(avanceCadena(cadena({ signo: -1 }), s, 2, 0)).toBeCloseTo(-2);
    expect(avanceCadena(cadena(), serie([cadena()], [30, 90, 150]), 1, 0)).toBeCloseTo(1); // desde q(0)
  });
});

describe("crearCadenas", () => {
  const mat = new THREE.MeshStandardMaterial();
  const pos = (im: THREE.InstancedMesh, k: number) => {
    const m = new THREE.Matrix4();
    im.getMatrixAt(k, m);
    return new THREE.Vector3().setFromMatrixPosition(m);
  };

  it("dos cadenas iguales comparten un juego de cuatro instancias", () => {
    const s = serie([cadena(), cadena({ pieza: "c2" })]);
    const r = crearCadenas(s, () => mat);
    expect(r.objetos).toHaveLength(4);
    expect(r.piezas).toEqual(["c1", "c2"]);
    const [rodillos, pernos, interiores, exteriores] = r.objetos as THREE.InstancedMesh[];
    expect([rodillos.count, pernos.count, interiores.count, exteriores.count]).toEqual([24, 24, 24, 24]);
    r.dispose();
  });

  it("cada pieza trae su material: se comparte por ASPECTO, no por objeto", () => {
    const mats: Record<string, THREE.Material> = {
      c1: new THREE.MeshStandardMaterial({ color: "#3b3e43" }),
      c2: new THREE.MeshStandardMaterial({ color: "#3b3e43" }),
      c3: new THREE.MeshStandardMaterial({ color: "#ff0000" }),
    };
    const s = serie([cadena(), cadena({ pieza: "c2" }), cadena({ pieza: "c3" })]);
    const r = crearCadenas(s, (p) => mats[p]);
    expect(r.objetos).toHaveLength(8); // dos juegos: el gris pavonado y el rojo
    r.dispose();
  });

  it("los rodillos van en el marco del lazo y avanzan con la junta", () => {
    const c = cadena();
    const r = crearCadenas(serie([c]), () => mat);
    const rodillos = r.objetos[0] as THREE.InstancedMesh;
    r.posar(0, 0);
    expect(pos(rodillos, 0).toArray()).toEqual([100 + c.puntos[0], c.puntos[1], 50]);
    r.posar(1, 0); // un paso: el rodillo 0 llega al lugar del 1
    const a = pos(rodillos, 0);
    expect(a.x).toBeCloseTo(100 + c.puntos[2]);
    expect(a.y).toBeCloseTo(c.puntos[3]);
    expect(rodillos.boundingBox).toBeNull(); // se recalcula para el encuadre y la sombra
    r.dispose();
  });

  it("una cadena con eslabones impares o sin lazo no se anima", () => {
    const impar = cadena({ puntos: lazo().slice(0, 22) });
    const r = crearCadenas(serie([impar]), () => mat);
    expect(r.objetos).toHaveLength(0);
    expect(r.piezas).toEqual([]);
  });
});
