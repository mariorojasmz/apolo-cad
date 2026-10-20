import { describe, expect, it } from "vitest";
import * as THREE from "three";
import type { FeatureOut } from "../types";
import { ACABADO_POR_DEFECTO, ACABADOS, TIPOS_RELIEVE, acabadoDe, albedoDe, claveAcabado } from "./acabados";
import { buildSolidMaterial, isGlass, resolveMaterialParams } from "./materials";
import { GENERADORES, LADO, alturas, uvCaja } from "./relieve";

/* La tabla de acabados (copia de core/apolo/library/apariencia.py, vigilada por
   tests/test_apariencia.py) y cómo la usa el visor. */

function pieza(extra: Partial<FeatureOut> = {}): FeatureOut {
  return {
    id: "f1", name: "Larguero (+Y)", visible: true, color: "#5b8def", volume_mm3: 1,
    bbox: { min: [0, 0, 0], max: [1, 1, 1] }, mesh: null, mesh_key: null, matrix: null,
    command_id: "c1", command_type: "create_box", component: null, cut_length: null, group: null,
    ...extra,
  };
}

describe("tabla de acabados", () => {
  it("cada acabado tiene parámetros PBR en rango y un color válido", () => {
    expect(Object.keys(ACABADOS).length).toBeGreaterThan(10);
    for (const [clave, ac] of Object.entries(ACABADOS)) {
      expect(ac.metalness, clave).toBeGreaterThanOrEqual(0);
      expect(ac.metalness, clave).toBeLessThanOrEqual(1);
      expect(ac.roughness, clave).toBeGreaterThanOrEqual(0);
      expect(ac.roughness, clave).toBeLessThanOrEqual(1);
      expect(ac.opacidad, clave).toBeGreaterThan(0);
      expect(ac.opacidad, clave).toBeLessThanOrEqual(1);
      if (ac.color !== null) expect(ac.color, clave).toMatch(/^#[0-9a-f]{6}$/);
      if (ac.relieve) {
        expect(TIPOS_RELIEVE, clave).toContain(ac.relieve.tipo);
        expect(ac.relieve.escala_mm, clave).toBeGreaterThan(0);
      }
    }
    expect(ACABADOS[ACABADO_POR_DEFECTO]).toBeDefined();
    expect(ACABADOS.vidrio.opacidad).toBeLessThan(1);
  });

  it("hay un generador procedural por cada tipo de relieve, y sólo esos", () => {
    expect(Object.keys(GENERADORES).sort()).toEqual([...TIPOS_RELIEVE].sort());
  });

  it("los mapas de relieve son deterministas y no planos", () => {
    for (const tipo of TIPOS_RELIEVE) {
      const a = alturas(tipo), b = alturas(tipo);
      expect(a.length).toBe(LADO * LADO * 4);
      expect(Array.from(a.slice(0, 64))).toEqual(Array.from(b.slice(0, 64)));
      const grises = Array.from({ length: LADO * LADO }, (_, i) => a[i * 4]);
      expect(Math.max(...grises) - Math.min(...grises), tipo).toBeGreaterThan(40);
    }
  });
});

describe("material de una pieza", () => {
  it("usa el acabado y el albedo que manda el servidor", () => {
    const f = pieza({ acabado: "caucho", albedo: "#1f2023" });
    expect(claveAcabado(f)).toBe("caucho");
    expect(resolveMaterialParams(f)).toEqual({ metalness: 0, roughness: ACABADOS.caucho.roughness });
    const m = buildSolidMaterial(f, resolveMaterialParams(f), false, []);
    expect("#" + m.color.getHexString()).toBe("#1f2023");
    expect(m.bumpMap).not.toBeNull(); // el caucho lleva relieve
  });

  it("sin acabado (o uno desconocido) cae al acero pintado con el color de la pieza", () => {
    expect(claveAcabado(pieza())).toBe(ACABADO_POR_DEFECTO);
    expect(claveAcabado(pieza({ acabado: "kriptonita" }))).toBe(ACABADO_POR_DEFECTO);
    expect(acabadoDe(pieza()).color).toBeNull();
    expect(albedoDe(pieza())).toBe("#5b8def");
  });

  it("el vidrio sale del acabado; sin acabado, del nombre", () => {
    expect(isGlass(pieza({ acabado: "vidrio" }))).toBe(true);
    expect(isGlass(pieza({ name: "Guía · acero templado", acabado: "acero_mecanizado" }))).toBe(false);
    expect(isGlass(pieza({ name: "Vidrio lateral" }))).toBe(true);
    const m = buildSolidMaterial(pieza({ acabado: "vidrio" }), { metalness: 0, roughness: 0 }, false, [], true);
    expect(m.transparent).toBe(true);
    expect(m.opacity).toBe(ACABADOS.vidrio.opacidad);
  });
});

describe("UV de caja para el relieve", () => {
  it("cada vértice recibe su UV en mm según la cara dominante", () => {
    const g = new THREE.BoxGeometry(100, 40, 20).toNonIndexed();
    g.deleteAttribute("uv");
    uvCaja(g);
    const uv = g.getAttribute("uv");
    expect(uv.count).toBe(g.getAttribute("position").count);
    let maxU = 0;
    for (let i = 0; i < uv.count; i++) maxU = Math.max(maxU, Math.abs(uv.getX(i)));
    expect(maxU).toBeCloseTo(50, 3); // en mm, no normalizado
  });
});
