import { beforeEach, describe, expect, it } from "vitest";
import * as THREE from "three";
import { crearReproductor, PUBLICAR_MS, type Mando } from "./reproductor";
import { useMarcha } from "./estado";
import type { SerieMarcha } from "./serie";

/* El reproductor de la marcha (plan visor-realista, D4) sobre mallas falsas: aplica T(t)·base a
   las piezas del cuerpo, hace nacer las cajas en su hora, avanza con la velocidad, salta, publica
   el tiempo a ≤ 10 Hz, para al final y deja todo como estaba. Y la línea de tiempo (`estado.ts`). */

const quatZ = (ang: number) => new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), ang);
const pq = (x: number, y: number, z: number, q = new THREE.Quaternion()) => [x, y, z, q.x, q.y, q.z, q.w];

/** 1 s a 2 Hz (3 muestras): el cuerpo gira 90° en Z alrededor del origen; la caja nace en t = 0,5. */
function serie(): SerieMarcha {
  return {
    hz: 2, duracion_s: 1, t: [0, 0.5, 1],
    cuerpos: { b_j: { junta: "j", piezas: ["tambor", "oculta"], poses: [...pq(0, 0, 0), ...pq(0, 0, 0, quatZ(Math.PI / 4)), ...pq(0, 0, 0, quatZ(Math.PI / 2))] } },
    productos: [{ name: "p_caja", producto: "caja", dims_mm: [100, 50, 20], desde: 1, poses: [...pq(0, 0, 900), ...pq(200, 0, 900)] }],
    juntas: {}, bandas: [], resumen: {}, avisos: [],
  };
}

function malla(x: number): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10));
  m.position.set(x, 0, 0);
  m.updateMatrix();
  m.userData.baseMatrix = new THREE.Matrix4().makeTranslation(x, 0, 0);
  m.userData.p0 = m.position.clone();
  m.userData.q0 = m.quaternion.clone();
  return m;
}

function armar(mando: Partial<Mando> = {}) {
  const meshes = new Map([["tambor", malla(100)], ["otra", malla(-50)]]);
  const escena = new THREE.Scene();
  const estado: Mando = { reproduciendo: false, velocidad: 1, salto: null, ...mando };
  const log = { saltos: 0, publicados: [] as [number, boolean][], posados: 0 };
  const r = crearReproductor(serie(), meshes, escena, () => estado, {
    saltoHecho: () => { log.saltos++; estado.salto = null; },
    publicar: (t, fin) => { log.publicados.push([t, fin]); if (fin) estado.reproduciendo = false; },
    alPosar: () => log.posados++,
  });
  const caja = () => escena.getObjectByName("marcha-productos")!.children[0] as THREE.Mesh;
  return { r, meshes, escena, estado, log, caja };
}

const pos = (m: THREE.Matrix4) => new THREE.Vector3().setFromMatrixPosition(m);

describe("crearReproductor", () => {
  it("nace en t = 0: piezas en su pose de diseño y la caja todavía oculta", () => {
    const { meshes, caja, log } = armar();
    const tambor = meshes.get("tambor")!;
    expect(tambor.matrixAutoUpdate).toBe(false);
    expect(pos(tambor.matrix).toArray()).toEqual([100, 0, 0]);
    expect(caja().visible).toBe(false);
    expect(meshes.get("otra")!.matrixAutoUpdate).toBe(true); // no es del cuerpo: no se toca
    expect(log.posados).toBe(1); // la sombra queda sucia
  });

  it("reproduce interpolando T(t)·base y la caja aparece en su hora", () => {
    const { r, meshes, caja } = armar({ reproduciendo: true });
    r.tick(1000);
    r.tick(1750); // +0,75 s
    expect(r.tiempo()).toBeCloseTo(0.75);
    const p = pos(meshes.get("tambor")!.matrix);
    const ang = (3 * Math.PI) / 8; // 67,5°: slerp entre 45° y 90°
    expect(p.x).toBeCloseTo(100 * Math.cos(ang));
    expect(p.y).toBeCloseTo(100 * Math.sin(ang));
    expect(caja().visible).toBe(true);
    expect(pos(caja().matrix).x).toBeCloseTo(100);
  });

  it("la velocidad escala el avance; en pausa no avanza ni vuelve a posar", () => {
    const { r, estado, log } = armar({ reproduciendo: true, velocidad: 0.5 });
    r.tick(1000);
    r.tick(1400);
    expect(r.tiempo()).toBeCloseTo(0.2);
    estado.reproduciendo = false;
    const posados = log.posados;
    r.tick(2000);
    r.tick(3000);
    expect(r.tiempo()).toBeCloseTo(0.2);
    expect(log.posados).toBe(posados);
    estado.reproduciendo = true; // al reanudar, el primer fotograma no salta la pausa
    r.tick(3100);
    expect(r.tiempo()).toBeCloseTo(0.2);
  });

  it("salta aunque esté en pausa y avisa que lo consumió", () => {
    const { r, estado, log, caja } = armar();
    estado.salto = 0.9;
    r.tick(500);
    expect(r.tiempo()).toBeCloseTo(0.9);
    expect(log.saltos).toBe(1);
    expect(log.publicados.at(-1)).toEqual([0.9, false]);
    expect(caja().visible).toBe(true);
  });

  it("publica el tiempo a la barra como mucho cada PUBLICAR_MS y para al final", () => {
    const { r, log } = armar({ reproduciendo: true, velocidad: 0.05 });
    r.tick(1000);
    for (let ms = 1016; ms < 1000 + 4 * PUBLICAR_MS; ms += 16) r.tick(ms);
    expect(log.publicados.length).toBeLessThanOrEqual(5);
    r.tick(1000 + 30000); // mucho después: pasa el final
    expect(r.tiempo()).toBe(1);
    expect(log.publicados.at(-1)).toEqual([1, true]);
  });

  it("restaurar devuelve las mallas a su pose base y retira las cajas", () => {
    const { r, meshes, escena, estado } = armar();
    estado.salto = 1;
    r.tick(10);
    r.restaurar();
    const tambor = meshes.get("tambor")!;
    expect(tambor.matrixAutoUpdate).toBe(true);
    expect(pos(tambor.matrix).toArray()).toEqual([100, 0, 0]);
    expect(escena.getObjectByName("marcha-productos")).toBeUndefined();
  });
});

describe("useMarcha (línea de tiempo)", () => {
  beforeEach(() => useMarcha.getState().quitar());

  it("cargar reproduce desde 0 y sube el token; quitar lo apaga", () => {
    const token = useMarcha.getState().token;
    useMarcha.getState().cargar(serie());
    expect(useMarcha.getState()).toMatchObject({ reproduciendo: true, t: 0, salto: 0, token: token + 1 });
    useMarcha.getState().quitar();
    expect(useMarcha.getState()).toMatchObject({ serie: null, reproduciendo: false, token: token + 2 });
  });

  it("saltar recorta al rango; reproducir en el final vuelve a empezar", () => {
    const m = useMarcha.getState();
    m.cargar(serie());
    m.saltar(5);
    expect(useMarcha.getState().salto).toBe(1);
    m.publicar(1, true);
    expect(useMarcha.getState().reproduciendo).toBe(false);
    m.alternar();
    expect(useMarcha.getState()).toMatchObject({ reproduciendo: true, salto: 0, t: 0 });
    m.alternar();
    expect(useMarcha.getState().reproduciendo).toBe(false);
  });

  it("sin serie, los mandos no hacen nada", () => {
    const m = useMarcha.getState();
    m.alternar();
    m.saltar(0.3);
    expect(useMarcha.getState()).toMatchObject({ reproduciendo: false, salto: null });
  });
});
