import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { crearReproductor, type Mando } from "./reproductor";
import type { FajaSerie, SerieMarcha } from "./serie";

/* La faja y las cadenas dentro del reproductor (plan visor-realista F3, D6): en marcha se ocultan
   la banda y la cadena del CAD, la cinta y los eslabones van al grupo de las piezas, los rodillos
   libres giran con la banda (también uno que viaja en un cuerpo) y al quitar la marcha todo vuelve. */

function malla(x: number, z = 0): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10), new THREE.MeshStandardMaterial());
  m.position.set(x, 0, z);
  m.updateMatrix();
  m.userData.baseMatrix = m.matrix.clone();
  m.userData.p0 = m.position.clone();
  m.userData.q0 = m.quaternion.clone();
  return m;
}

const ruta: number[] = [];
for (let k = 0; k <= 8; k++) { const a = -Math.PI / 2 + (k * Math.PI) / 8; ruta.push(1000 + 50 * Math.cos(a), 50 * Math.sin(a)); }
for (let k = 0; k <= 8; k++) { const a = Math.PI / 2 + (k * Math.PI) / 8; ruta.push(50 * Math.cos(a), 50 * Math.sin(a)); }

const faja: FajaSerie = {
  pieza: "banda", junta: "j", marco: { origen: [0, 0, 0], u: [1, 0, 0], w: [0, 0, 1], v: [0, -1, 0] },
  ruta, espesor: 4, ancho: 500, v_centro: 0, largo_mm: 2314, signo: -1, tramos: [], envueltos: [], apoyos: [],
  tension: {},
  rodillos: [
    { pieza: "cola", centro: [0, 0, 0], eje: [0, -1, 0], radio_mm: 48 },
    { pieza: "tensor", centro: [1000, 0, 0], eje: [0, -1, 0], radio_mm: 48 },
  ],
};

/** 1 s: la banda corre 0,2 m/s; el «tensor» va en un cuerpo que se corre 10 mm en X. */
function serie(): SerieMarcha {
  const pq = (x: number) => [x, 0, 0, 0, 0, 0, 1];
  return {
    hz: 1, duracion_s: 1, t: [0, 1], productos: [], resumen: {}, avisos: [],
    cuerpos: { b_t: { junta: "jt", piezas: ["tensor"], poses: [...pq(0), ...pq(10)] } },
    juntas: { jt: { tipo: "prismatica", unidad: "mm", q: [0, 10] } },
    bandas: [{ pieza: "banda", junta: "j", radio_mm: 52, direccion: [1, 0, 0], v_m_s: [0.2, 0.2] }],
    fajas: [faja],
  };
}

function armar(ocultaBanda = false) {
  const meshes = new Map([["banda", malla(500)], ["cola", malla(0, 48)], ["tensor", malla(1000, 48)]]);
  meshes.get("banda")!.visible = !ocultaBanda;
  const escena = new THREE.Scene();
  const piezas = new THREE.Group();
  const estado: Mando = { reproduciendo: false, velocidad: 1, salto: null };
  const r = crearReproductor(serie(), meshes, escena, () => estado, {
    saltoHecho: () => { estado.salto = null; }, publicar: () => {}, alPosar: () => {},
  }, 0, piezas);
  return { r, meshes, piezas, estado };
}

const pos = (m: THREE.Matrix4) => new THREE.Vector3().setFromMatrixPosition(m);

describe("la faja en el reproductor", () => {
  it("oculta la banda del CAD y pone la cinta en el grupo de las piezas", () => {
    const { meshes, piezas, r } = armar();
    expect(meshes.get("banda")!.visible).toBe(false);
    expect(piezas.children).toHaveLength(1);
    expect(piezas.children[0].userData.marcha).toBe(true);
    r.restaurar();
    expect(meshes.get("banda")!.visible).toBe(true);
    expect(piezas.children).toHaveLength(0);
  });

  it("los rodillos libres giran recorrido / radio; el que va en un cuerpo además se desplaza", () => {
    const { meshes, r, estado } = armar();
    estado.salto = 1;
    r.tick(16);
    const ang = 200 / 48; // la banda corrió 200 mm con la cara de arriba hacia +X
    const cola = pos(meshes.get("cola")!.matrix); // su centro de malla está 48 arriba del eje
    expect(cola.x).toBeCloseTo(48 * Math.sin(ang)); // lo de arriba va con la banda
    expect(cola.z).toBeCloseTo(48 * Math.cos(ang));
    const tensor = pos(meshes.get("tensor")!.matrix);
    expect(tensor.x).toBeCloseTo(1010 + 48 * Math.sin(ang));
    expect(tensor.z).toBeCloseTo(48 * Math.cos(ang));
    r.restaurar();
    expect(meshes.get("cola")!.matrixAutoUpdate).toBe(true);
    expect(pos(meshes.get("cola")!.matrix).toArray()).toEqual([0, 0, 48]);
  });

  it("el piñón sin junta (el del motor) gira con la cadena y la cadena del CAD se oculta", () => {
    const puntos: number[] = [];
    for (const a of [90, 150, 210, 270]) puntos.push(10 * Math.cos((a * Math.PI) / 180), 10 * Math.sin((a * Math.PI) / 180));
    puntos.push(10, -10, 20, -10);
    for (const a of [270, 330, 30, 90]) puntos.push(30 + 10 * Math.cos((a * Math.PI) / 180), 10 * Math.sin((a * Math.PI) / 180));
    puntos.push(20, 10, 10, 10);
    const s: SerieMarcha = {
      hz: 1, duracion_s: 1, t: [0, 1], cuerpos: {}, productos: [], bandas: [], resumen: {}, avisos: [],
      juntas: { j: { tipo: "continua", unidad: "grados", q: [0, 60] } },
      cadenas: [{
        pieza: "cadena", junta: "j", lado: "b", z: 6, signo: 1, pinones_libres: [{ pieza: "motor", lado: "a", z: 6 }],
        marco: [1, 0, 0, 100, 0, 1, 0, 0, 0, 0, 1, 50, 0, 0, 0, 1], paso: 10, za: 6, zb: 6, centro_b: [30, 0],
        puntos, asentados_a: [0, 4], asentados_b: [6, 4], rodillo_d: 6, perno_d: 3, alto_placa: 8, espesor_placa: 1,
        capas: { rodillos: [[-2, 2]], interiores: [[-3, -2], [2, 3]], exteriores: [[-4.1, -3.1], [3.1, 4.1]], perno: [-5, 5] },
      }],
    };
    const motor = malla(110, 50); // a 10 mm del eje del piñón A (100, 0, 50)
    const meshes = new Map([["cadena", malla(115, 50)], ["motor", motor]]);
    const piezas = new THREE.Group();
    const estado: Mando = { reproduciendo: false, velocidad: 1, salto: 1 };
    const r = crearReproductor(s, meshes, new THREE.Scene(), () => estado, {
      saltoHecho: () => { estado.salto = null; }, publicar: () => {}, alPosar: () => {},
    }, 0, piezas);
    expect(meshes.get("cadena")!.visible).toBe(false);
    expect(piezas.children).toHaveLength(4); // rodillos, pernos, placas interiores y exteriores
    r.tick(16); // q = 60°: un eslabón, 1/6 de vuelta del piñón de 6 dientes
    const p = pos(motor.matrix);
    expect(p.x).toBeCloseTo(100 + 10 * Math.cos(Math.PI / 3));
    expect(p.y).toBeCloseTo(10 * Math.sin(Math.PI / 3));
    r.restaurar();
    expect(meshes.get("cadena")!.visible).toBe(true);
    expect(pos(motor.matrix).toArray()).toEqual([110, 0, 50]);
  });

  it("una banda oculta por el usuario sigue oculta y sin cinta", () => {
    const { meshes, piezas } = armar(true);
    expect(meshes.get("banda")!.visible).toBe(false);
    expect(piezas.children).toHaveLength(0);
  });
});
