import { describe, expect, it } from "vitest";
import * as THREE from "three";
import type { FeatureOut } from "../types";
import { ACABADOS, TIPOS_TEXTURA } from "./acabados";
import { buildSolidMaterial, resolveMaterialParams } from "./materials";
import { LADO } from "./relieve";
import { GENERADORES_TEXTURA, mapaTextura, mapasTextura } from "./textura";

/* Texturas procedurales de los acabados (video-realista D2): se generan en el navegador desde
   los parámetros de la tabla (copia de core/apolo/library/apariencia.py). */

function pieza(acabado: string, albedo: string): FeatureOut {
  return {
    id: "f1", name: "Pieza", visible: true, color: "#5b8def", volume_mm3: 1,
    bbox: { min: [0, 0, 0], max: [1, 1, 1] }, mesh: null, mesh_key: null, matrix: null,
    command_id: "c1", command_type: "create_box", component: null, cut_length: null, group: null,
    acabado, albedo,
  };
}
const material = (acabado: string, albedo = "#808080", wire = false, glass = false) => {
  const f = pieza(acabado, albedo);
  return buildSolidMaterial(f, resolveMaterialParams(f), wire, [], glass);
};

describe("texturas procedurales", () => {
  it("hay un generador por cada tipo de textura de la tabla, y sólo esos", () => {
    expect(Object.keys(GENERADORES_TEXTURA).sort()).toEqual([...TIPOS_TEXTURA].sort());
    for (const ac of Object.values(ACABADOS)) {
      if (ac.textura) expect(TIPOS_TEXTURA).toContain(ac.textura.tipo);
    }
  });

  it("los mapas son deterministas, varían lo pedido y no son planos", () => {
    for (const tipo of TIPOS_TEXTURA) {
      for (const canal of ["color", "rugosidad"] as const) {
        const a = mapaTextura(GENERADORES_TEXTURA[tipo][canal], 0.4);
        const b = mapaTextura(GENERADORES_TEXTURA[tipo][canal], 0.4);
        expect(a.datos.length).toBe(LADO * LADO * 4);
        expect(Array.from(a.datos.slice(0, 256))).toEqual(Array.from(b.datos.slice(0, 256)));
        const v = Array.from({ length: LADO * LADO }, (_, i) => a.datos[i * 4]);
        // factor = 1 − 0,4 · (1 − patrón) ∈ [0,6 ; 1]
        expect(Math.min(...v), `${tipo} ${canal}`).toBeGreaterThanOrEqual(Math.floor(0.6 * 255));
        expect(Math.max(...v) - Math.min(...v), `${tipo} ${canal}`).toBeGreaterThan(20);
        expect(a.promedio).toBeGreaterThan(0.6);
        expect(a.promedio).toBeLessThan(1);
      }
    }
  });

  it("las lentejuelas son cristales: hay zonas de tono parejo, no ruido de píxel", () => {
    const m = mapaTextura(GENERADORES_TEXTURA.lentejuelas.color, 1);
    let iguales = 0;
    for (let i = 0; i < LADO * LADO - 1; i++) if (Math.abs(m.datos[i * 4] - m.datos[i * 4 + 4]) < 30) iguales++;
    expect(iguales / (LADO * LADO)).toBeGreaterThan(0.8);
  });

  it("los mapas se comparten entre piezas del mismo acabado", () => {
    const t = ACABADOS.galvanizado.textura!;
    expect(mapasTextura(t)).toBe(mapasTextura(t));
    expect(mapasTextura({ ...t, tipo: "inexistente" })).toBeNull();
  });
});

describe("material con textura", () => {
  it("galvanizado: color y brillo variables, con el tono medio de la tabla", () => {
    const m = material("galvanizado", "#b4bac0");
    expect(m.map).not.toBeNull();
    expect(m.roughnessMap).not.toBeNull();
    const mapas = mapasTextura(ACABADOS.galvanizado.textura!)!;
    // el color se compensa por el promedio del mapa: color × promedio = albedo
    const base = new THREE.Color("#b4bac0");
    expect(m.color.r / mapas.compensaColor).toBeCloseTo(base.r, 5);
    expect(m.roughness / mapas.compensaRugosidad).toBeCloseTo(ACABADOS.galvanizado.roughness, 5);
  });

  it("acero cepillado: material físico con anisotropía", () => {
    for (const clave of ["inox_cepillado", "acero_mecanizado", "aluminio"]) {
      const m = material(clave);
      expect(m).toBeInstanceOf(THREE.MeshPhysicalMaterial);
      expect((m as THREE.MeshPhysicalMaterial).anisotropy).toBeCloseTo(ACABADOS[clave].textura!.anisotropia);
    }
    expect(material("galvanizado")).not.toBeInstanceOf(THREE.MeshPhysicalMaterial);
  });

  it("pintura y goma: sólo el brillo varía; el color es el de la pieza", () => {
    for (const clave of ["acero_pintado", "caucho"]) {
      const m = material(clave, "#2b5c9e");
      expect(m.map, clave).toBeNull();
      expect(m.roughnessMap, clave).not.toBeNull();
      expect("#" + m.color.getHexString()).toBe("#2b5c9e");
    }
  });

  it("ni el alambre ni el vidrio llevan textura; un acabado sin textura queda liso", () => {
    expect(material("galvanizado", "#b4bac0", true).map).toBeNull();
    expect(material("vidrio", "#dceaf2", false, true).roughnessMap).toBeNull();
    const pav = material("pavonado", "#3b3e43");
    expect(pav.map).toBeNull();
    expect(pav.roughnessMap).toBeNull();
  });
});
