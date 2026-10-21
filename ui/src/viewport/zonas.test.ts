import { describe, expect, it } from "vitest";
import * as THREE from "three";
import type { FeatureOut, Mesh as MeshPayload, SceneOut, ZonaOut } from "../types";
import { mergeSceneDelta } from "../state/sceneDelta";
import { ACABADOS } from "./acabados";
import { applyAppearance, appearanceSig, buildMesh, disposeMesh, type SharedGeom } from "./meshes";
import { gruposDeZonas, liberarMaterial, materialesDe, zonasDelDelta } from "./zonas";

/* Zonas de acabado en el visor (plan seta-de-emergencia, F2: D2 y D3). Una pieza con zonas es
   UNA malla con `geometry.groups` y un arreglo de materiales, uno por zona; el albedo de cada
   zona lo resuelve el servidor (una zona de norma no toma el color asignado). */

/** Caja de 2×2×2 en 12 triángulos (6 caras × 2), indexada como la manda el servidor. */
function cajaPayload(): MeshPayload {
  const positions = [
    -1, -1, -1, 1, -1, -1, 1, 1, -1, -1, 1, -1,
    -1, -1, 1, 1, -1, 1, 1, 1, 1, -1, 1, 1,
  ];
  const indices = [
    0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
    2, 3, 7, 2, 7, 6, 1, 2, 6, 1, 6, 5, 0, 4, 7, 0, 7, 3,
  ];
  return { positions, indices };
}

const ROJO = ACABADOS.plastico_rojo_seguridad.color!;
const AMARILLO = ACABADOS.plastico_amarillo_seguridad.color!;
const NEGRO = ACABADOS.plastico_negro.color!;

/** Seta de juguete: frente rojo (fijo), leyenda amarilla (fijo), caja pintable y collar negro. */
function zonasSeta(caja = AMARILLO): ZonaOut[] {
  return [
    { acabado: "plastico_rojo_seguridad", albedo: ROJO, desde: 0, hasta: 2 },
    { acabado: "plastico_amarillo_seguridad", albedo: AMARILLO, desde: 2, hasta: 4 },
    { acabado: "plastico_amarillo_seguridad", albedo: caja, desde: 4, hasta: 10 },
    { acabado: "plastico_negro", albedo: NEGRO, desde: 10, hasta: 12 },
  ];
}

function pieza(extra: Partial<FeatureOut> = {}): FeatureOut {
  return {
    id: "s1", name: "Parada de emergencia", visible: true, color: "#5b8def", volume_mm3: 8,
    bbox: { min: [-1, -1, -1], max: [1, 1, 1] }, mesh: cajaPayload(), mesh_key: null,
    matrix: null, command_id: "c1", command_type: "insert_component", component: "ESTOP-40-CAJA",
    cut_length: null, group: null, acabado: "acero_pintado", albedo: "#5b8def", rev: 1, ...extra,
  };
}

const construir = (f: FeatureOut, defs: Record<string, MeshPayload> | null = null,
  shared = new Map<string, SharedGeom>()) => buildMesh(f, "solid", [], defs, shared, null);

const colorDe = (m: THREE.Material) => `#${(m as THREE.MeshStandardMaterial).color.getHexString()}`;

describe("grupos de las zonas", () => {
  it("la suma de los rangos cubre todos los índices de la malla, sin huecos ni solapes", () => {
    const grupos = gruposDeZonas(zonasSeta(), 12)!;
    expect(grupos.map((g) => g.materialIndex)).toEqual([0, 1, 2, 3]);
    expect(grupos[0].start).toBe(0);
    expect(grupos.reduce((s, g) => s + g.count, 0)).toBe(12 * 3); // vértices: no indexada
    for (let i = 1; i < grupos.length; i++) {
      expect(grupos[i].start).toBe(grupos[i - 1].start + grupos[i - 1].count);
    }
  });

  it("unas zonas que no describen la malla se descartan (un triángulo sin grupo no se vería)", () => {
    const z = zonasSeta();
    expect(gruposDeZonas(z, 13)).toBeNull(); // no llegan al final
    expect(gruposDeZonas([z[0], ...z.slice(2)], 12)).toBeNull(); // hueco
    expect(gruposDeZonas([{ ...z[0], hasta: 3 }, ...z.slice(1)], 12)).toBeNull(); // solape
    expect(gruposDeZonas([{ ...z[0], desde: 0, hasta: 0 }, ...z], 12)).toBeNull(); // vacía
    expect(gruposDeZonas([], 12)).toBeNull();
    expect(gruposDeZonas(undefined, 12)).toBeNull();
  });
});

describe("una pieza con zonas en el visor", () => {
  it("lleva un material por zona y el de cada grupo es el de su zona", () => {
    const zonas = zonasSeta();
    const mesh = construir(pieza({ zonas }));
    const mats = mesh.material as THREE.Material[];
    expect(Array.isArray(mats)).toBe(true);
    expect(mats).toHaveLength(zonas.length);
    const geom = mesh.geometry;
    expect(geom.groups).toHaveLength(zonas.length);
    expect(geom.groups.reduce((s, g) => s + g.count, 0)).toBe(geom.getAttribute("position").count);
    geom.groups.forEach((g, i) => {
      const zona = zonas[i];
      const mat = mats[g.materialIndex!] as THREE.MeshStandardMaterial;
      expect(g.start).toBe(zona.desde * 3);
      expect(colorDe(mat)).toBe(zona.albedo);
      expect(mat.roughness).toBeCloseTo(ACABADOS[zona.acabado].roughness);
      expect(mat.metalness).toBeCloseTo(ACABADOS[zona.acabado].metalness);
    });
    // los triángulos de cada grupo son los del rango de su zona (la geometría no se reordena)
    expect(geom.getAttribute("position").count).toBe(12 * 3);
    disposeMesh(mesh);
  });

  it("cada zona lleva la textura procedural de su acabado", () => {
    const zonas: ZonaOut[] = [
      { acabado: "galvanizado", albedo: ACABADOS.galvanizado.color!, desde: 0, hasta: 6 },
      { acabado: "plastico_negro", albedo: NEGRO, desde: 6, hasta: 12 },
    ];
    const [galv, negro] = construir(pieza({ zonas })).material as THREE.MeshStandardMaterial[];
    expect(ACABADOS.galvanizado.textura).not.toBeNull();
    expect(galv.map ?? galv.roughnessMap).not.toBeNull();
    expect(negro.map).toBeNull();
    expect(negro.roughnessMap).toBeNull();
  });

  it("el color asignado a la pieza no pinta lo fijo: cada zona usa el albedo que manda el servidor", () => {
    // set_color «#00aa44»: el servidor repinta sólo la caja pintable; la seta y la leyenda no
    const zonas = zonasSeta("#00aa44");
    const f = pieza({ color: "#00aa44", albedo: "#00aa44", zonas });
    const mats = construir(f).material as THREE.Material[];
    expect(mats.map(colorDe)).toEqual([ROJO, AMARILLO, "#00aa44", NEGRO]);
  });

  it("el delta repinta en sitio: rangos de la geometría que ya está, apariencia nueva", () => {
    const antes = pieza({ zonas: zonasSeta() });
    const prev: SceneOut = { features: [antes], definitions: {}, document: {} as SceneOut["document"] };
    const igual = {
      id: "s1", rev: 1, same: true, name: antes.name, color: "#00aa44", visible: true,
      group: null, is_guide: false, acabado: "acero_pintado", albedo: "#00aa44",
      // rangos que no se usan: la geometría del visor es la de `prev`
      zonas: zonasSeta("#00aa44").map((z) => ({ ...z, desde: 99, hasta: 99 })),
    } as unknown as FeatureOut;
    const despues = mergeSceneDelta(prev, { ...prev, features: [igual] }).features[0];
    expect(despues.zonas!.map((z) => [z.desde, z.hasta])).toEqual(zonasSeta().map((z) => [z.desde, z.hasta]));
    expect(despues.mesh).toBe(antes.mesh);

    const mesh = construir(antes);
    expect(appearanceSig(despues)).not.toBe(appearanceSig(antes));
    applyAppearance(mesh, despues, "solid", [], null);
    expect((mesh.material as THREE.Material[]).map(colorDe)).toEqual([ROJO, AMARILLO, "#00aa44", NEGRO]);
    disposeMesh(mesh);
  });

  it("las instancias comparten la geometría partida de su definición", () => {
    const defs = { "k|estop": cajaPayload() };
    const shared = new Map<string, SharedGeom>();
    const inst = (id: string, x: number) => pieza({
      id, mesh: null, mesh_key: "k|estop", zonas: zonasSeta(),
      matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, 0, 0, 1],
    });
    const a = construir(inst("a", 0), defs, shared);
    const b = construir(inst("b", 50), defs, shared);
    expect(a.geometry).toBe(b.geometry);
    expect(a.geometry.groups).toHaveLength(4);
    expect(materialesDe(a.material)).toHaveLength(4);
    expect(materialesDe(b.material)).toHaveLength(4);
    expect(a.material).not.toBe(b.material); // los materiales son de cada pieza
  });
});

describe("una pieza sin zonas", () => {
  it("sigue con un solo material, sin grupos y con la firma de apariencia de siempre", () => {
    const f = pieza({ component: null });
    const mesh = construir(f);
    expect(Array.isArray(mesh.material)).toBe(false);
    expect(mesh.geometry.groups).toHaveLength(0);
    expect(colorDe(mesh.material as THREE.Material)).toBe("#5b8def");
    expect(appearanceSig(f)).toBe(`#5b8def|acero_pintado|#5b8def|${f.name}|0`);
    disposeMesh(mesh);
  });

  it("si sus zonas no cubren la malla, se ve de un solo acabado (no desaparecen triángulos)", () => {
    const mesh = construir(pieza({ zonas: zonasSeta().slice(0, 3) }));
    expect(Array.isArray(mesh.material)).toBe(false);
    expect(mesh.geometry.groups).toHaveLength(0);
  });

  it("el delta no le agrega la clave `zonas`", () => {
    const antes = pieza({ component: null });
    const prev: SceneOut = { features: [antes], definitions: {}, document: {} as SceneOut["document"] };
    const igual = { id: "s1", rev: 1, same: true, name: "x", color: "#111111", visible: true,
      group: null, is_guide: false, acabado: "acero_pintado", albedo: "#111111" } as unknown as FeatureOut;
    const despues = mergeSceneDelta(prev, { ...prev, features: [igual] }).features[0];
    expect("zonas" in despues).toBe(false);
    expect(zonasDelDelta(undefined, undefined)).toBeUndefined();
  });
});

describe("materiales de una malla", () => {
  it("uno o un arreglo se recorren y liberan igual", () => {
    const a = new THREE.MeshStandardMaterial();
    const b = new THREE.MeshStandardMaterial();
    expect(materialesDe(a)).toEqual([a]);
    expect(materialesDe([a, b])).toEqual([a, b]);
    expect(materialesDe(null)).toEqual([]);
    let liberados = 0;
    for (const m of [a, b]) m.addEventListener("dispose", () => liberados++);
    liberarMaterial([a, b]);
    expect(liberados).toBe(2);
  });
});
