import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { ACABADOS } from "../viewport/acabados";
import type { ZonaOut } from "../types";
import { EMISION_PILOTO } from "./mandos";
import { instalarMandos3D } from "./mandos3d";
import type { PilotoVivo } from "./protocolo";

/* El piloto encendido en el 3D (pendientes de la D-a de pedidos-de-extensiones-ii): brilla sólo
   su lente —la zona `de_color` de su pieza— en el tono del acabado de su color; sin zonas de
   color, la pieza entera, como antes. Al quitar la sesión vuelve el material original. */

const H1: PilotoVivo = { designacion: "-H1", ref: "PILOTO-24V-AMBAR", color: "ambar", pieza: "c1", senal: "-H1.encendido" };

function zona(nombre: string, desde: number, hasta: number, de_color?: boolean): ZonaOut {
  return { acabado: "plastico_negro", albedo: "#1c1d20", desde, hasta, zona: nombre, ...(de_color ? { de_color } : {}) };
}

function pieza(nZonas: number): THREE.Mesh {
  const mats = Array.from({ length: nZonas }, () => new THREE.MeshStandardMaterial());
  return new THREE.Mesh(new THREE.BufferGeometry(), nZonas === 1 ? mats[0] : mats);
}

function instalar(mesh: THREE.Mesh, zonas: ZonaOut[] | undefined, valor: { v: number }) {
  return instalarMandos3D({
    contenedor: {} as HTMLElement,
    canvas: {} as HTMLCanvasElement,
    camara: () => new THREE.PerspectiveCamera(),
    meshes: new Map([["c1", mesh]]),
    mandos: [],
    pilotos: [H1],
    valor: () => valor.v,
    estado: () => ({}),
    enviar: () => {},
    zonas: () => zonas,
  });
}

/** Lo que emite un material: 0 si su emisivo es negro (el `emissiveIntensity` por defecto es 1). */
const brillo = (m: THREE.Material) => {
  const s = m as THREE.MeshStandardMaterial;
  return s.emissive.getHex() === 0 ? 0 : s.emissiveIntensity;
};

describe("piloto encendido en el 3D", () => {
  it("brilla sólo la lente, en el tono del acabado de su color", () => {
    const mesh = pieza(3);
    const original = mesh.material;
    const v = { v: 1 };
    const m3d = instalar(mesh, [zona("frente", 0, 4, true), zona("bisel", 4, 8), zona("cuerpo", 8, 12)], v);
    m3d.tick(1000);
    const [lente, bisel, cuerpo] = mesh.material as THREE.MeshStandardMaterial[];
    expect(brillo(lente)).toBe(EMISION_PILOTO);
    expect("#" + lente.emissive.getHexString()).toBe(ACABADOS.plastico_ambar.color);
    expect(brillo(bisel)).toBe(0);
    expect(brillo(cuerpo)).toBe(0);
    v.v = 0;
    m3d.tick(2000);
    expect(brillo(lente)).toBe(0);
    m3d.quitar();
    expect(mesh.material).toBe(original);
  });

  it("sin zona de color (pieza de un solo material o servidor anterior), brilla entera", () => {
    const sola = pieza(1);
    instalar(sola, undefined, { v: 1 }).tick(1000);
    expect(brillo(sola.material as THREE.Material)).toBe(EMISION_PILOTO);

    const sinMarca = pieza(3);
    instalar(sinMarca, [zona("frente", 0, 4), zona("bisel", 4, 8), zona("cuerpo", 8, 12)], { v: 1 }).tick(1000);
    expect((sinMarca.material as THREE.Material[]).map(brillo)).toEqual([EMISION_PILOTO, EMISION_PILOTO, EMISION_PILOTO]);
  });
});
