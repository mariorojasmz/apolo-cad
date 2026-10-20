import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { correrTextura, crearFajas, geometriaFaja, giroRodillo, recorridoEn, recorridos, texturaEmpalme } from "./faja";
import type { FajaSerie, SerieMarcha } from "./serie";

/* La faja con su forma real (plan visor-realista F3, D6): la cinta sale de la ruta del servidor,
   su textura corre el recorrido de la banda y los rodillos libres giran recorrido / radio. */

/** Lazo de pista en el plano XZ (u = +X, w = +Z, v = −Y: diestro), antihorario. */
function faja(extra: Partial<FajaSerie> = {}): FajaSerie {
  const ruta: number[] = [];
  for (let k = 0; k <= 8; k++) { const a = -Math.PI / 2 + (k * Math.PI) / 8; ruta.push(1000 + 50 * Math.cos(a), 50 * Math.sin(a)); }
  for (let k = 0; k <= 8; k++) { const a = Math.PI / 2 + (k * Math.PI) / 8; ruta.push(50 * Math.cos(a), 50 * Math.sin(a)); }
  return {
    pieza: "banda", junta: "j", marco: { origen: [0, 0, 800], u: [1, 0, 0], w: [0, 0, 1], v: [0, -1, 0] },
    ruta, espesor: 4, ancho: 500, v_centro: 0, largo_mm: 2 * 1000 + 2 * Math.PI * 50, signo: -1,
    tramos: [], envueltos: [], apoyos: [], tension: {},
    rodillos: [{ pieza: "cola", centro: [0, 0, 800], eje: [0, -1, 0], radio_mm: 48 }],
    ...extra,
  };
}

describe("recorrido de la banda", () => {
  it("integra la velocidad (m/s) en mm por trapecios y aplica el sentido de la ruta", () => {
    const s = recorridos([0, 1, 2], [0.5, 0.5, 1.5]);
    expect(s).toEqual([0, 500, 1500]);
    expect(recorridoEn(faja(), s, 1, 0.5)).toBe(-1000); // la cara de arriba va a +u: horario
    expect(recorridoEn(faja({ signo: 1 }), s, 5, 0)).toBe(1500); // fuera del rango, el último
  });
});

describe("geometriaFaja", () => {
  const g = geometriaFaja(faja());
  const n = faja().ruta.length / 2;

  it("cuatro caras (afuera, adentro y cantos) que cierran el lazo con u en mm", () => {
    expect(g.getAttribute("position").count).toBe(4 * (n + 1) * 2);
    const uv = g.getAttribute("uv");
    expect(uv.getX(2 * n)).toBeCloseTo(2 * 1000 + 16 * 2 * 50 * Math.sin(Math.PI / 16), 3); // el polígono
    expect(uv.getY(1) - uv.getY(0)).toBeCloseTo(500); // a lo ancho, en mm
  });

  it("la cara de afuera mira hacia afuera del lazo y la cinta tiene su ancho y espesor", () => {
    const pos = g.getAttribute("position"), nor = g.getAttribute("normal");
    const centro = new THREE.Vector3(500, 0, 800);
    for (let k = 0; k < 2 * (n + 1); k += 5) {
      const p = new THREE.Vector3().fromBufferAttribute(pos, k).sub(centro).setY(0);
      const m = new THREE.Vector3().fromBufferAttribute(nor, k);
      expect(p.dot(m)).toBeGreaterThan(0);
    }
    const bb = g.boundingBox!;
    expect(bb.max.y - bb.min.y).toBeCloseTo(500);
    expect(bb.max.z).toBeCloseTo(800 + 50 + 2, 1); // Float32
  });
});

describe("textura que corre", () => {
  it("el empalme que estaba en u = 0 queda en u = s", () => {
    const tex = texturaEmpalme(2314);
    for (const s of [0, 120, 2500, -700]) {
      correrTextura(tex, s);
      const x = s * tex.repeat.x + tex.offset.x; // la coordenada de textura en u = s
      expect(x - Math.round(x)).toBeCloseTo(0, 9);
      expect(tex.offset.x).toBeGreaterThanOrEqual(0);
      expect(tex.offset.x).toBeLessThan(1);
    }
  });
});

describe("giroRodillo", () => {
  it("gira recorrido / radio alrededor de su eje por su centro", () => {
    const r = faja().rodillos[0];
    const m = giroRodillo(r, (Math.PI / 2) * 48, new THREE.Matrix4());
    const arriba = new THREE.Vector3(0, 0, 848).applyMatrix4(m);
    // 90° sobre −Y: lo de arriba (+Z) va a −X, como la banda que sube por la cola
    expect(arriba.x).toBeCloseTo(-48);
    expect(arriba.z).toBeCloseTo(800);
    const vuelta = giroRodillo(r, 2 * Math.PI * 48, new THREE.Matrix4());
    expect(new THREE.Vector3(5, 7, 811).applyMatrix4(vuelta).toArray().map((v) => +v.toFixed(6))).toEqual([5, 7, 811]);
  });
});

describe("crearFajas", () => {
  const s = (f: FajaSerie): SerieMarcha => ({
    hz: 1, duracion_s: 1, t: [0, 1], cuerpos: {}, productos: [], juntas: {}, resumen: {}, avisos: [],
    bandas: [{ pieza: "banda", junta: "j", radio_mm: 52, direccion: [1, 0, 0], v_m_s: [0.2, 0.2] }],
    fajas: [f],
  });

  it("clona el material de la banda con su relieve y le suma el empalme que corre", () => {
    const relieve = new THREE.DataTexture(new Uint8Array(4), 1, 1);
    relieve.repeat.set(1 / 7, 1 / 7);
    const base = new THREE.MeshStandardMaterial({ color: "#2f5b3b", bumpMap: relieve });
    const r = crearFajas(s(faja()), () => base);
    expect(r.piezas).toEqual(["banda"]);
    const mat = (r.objetos[0] as THREE.Mesh).material as THREE.MeshStandardMaterial;
    expect(mat).not.toBe(base);
    expect(mat.bumpMap).not.toBe(relieve);
    expect(mat.map).toBeTruthy();
    const rec = r.posar(1, 0);
    expect([...rec.entries()]).toEqual([["banda", -200]]); // la cara de arriba fue 200 mm a +u
    expect(relieve.offset.x).toBe(0); // el relieve de las demás piezas no corre
    expect(mat.bumpMap!.offset.x).toBeCloseTo((200 / 7) % 1);
    r.dispose();
  });

  it("una ruta vacía no se dibuja", () => {
    expect(crearFajas(s(faja({ ruta: [0, 0, 1, 1] })), () => null).objetos).toHaveLength(0);
  });
});
