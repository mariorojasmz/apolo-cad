import { describe, expect, it } from "vitest";
import {
  aparicionesPorCuadro, direccion, intensidadResalte, tiempoMarcha, tramoDe, validarPlan, type PlanGuion,
} from "./planGuion";

/* El plan del guion (video-realista D5) lo arma la API; aquí sólo se lee: qué parte va en cada
   cuadro, la dirección de la cámara con la convención de VTK, el resaltado y el reloj de la
   marcha, que no se pasa del final de la serie. */

function plan(extra: Partial<PlanGuion> = {}): PlanGuion {
  const n = 10;
  return {
    version: 1, titulo: "Faja", video: { ancho: 1920, alto: 1080, fps: 10 }, cuadros: n,
    tramos: [
      { parte: "portada", inicio: 0, fin: 2, etapa: null, cruza: false },
      { parte: "etapa", inicio: 2, fin: 6, etapa: 0, cruza: true },
      { parte: "marcha", inicio: 6, fin: 8, etapa: null, cruza: false },
      { parte: "orbita", inicio: 8, fin: 10, etapa: null, cruza: true },
    ],
    etapas: [{ titulo: "Bastidor", texto: "" }], ids: ["a", "b"],
    apariciones: [{ cuadro: 2, ids: ["a"] }, { cuadro: 4, ids: ["b"] }],
    marcha: { inicio: 6, fin: 8, duracion_s: 0.2, escenario: null },
    camara: { elevacion: 22, azimut_inicial: -55 }, resalte_s: 1.2, proyecto: 7,
    cuadro: {
      az: Array(n).fill(0), luz: Array(n).fill(1), mezcla: Array(n).fill(null), rotulo: Array(n).fill(0),
      marcha_t: [null, null, null, null, null, null, 0, 0.1, 0.2, 0.3],
    },
    ...extra,
  };
}

describe("plan del guion", () => {
  it("cada cuadro cae en su parte, también en los bordes", () => {
    const p = plan();
    expect([0, 1, 2, 5, 6, 7, 8, 9].map((n) => tramoDe(p, n).parte)).toEqual(
      ["portada", "portada", "etapa", "etapa", "marcha", "marcha", "orbita", "orbita"]);
  });

  it("rechaza un plan que no cubre todos los cuadros", () => {
    expect(() => validarPlan(plan())).not.toThrow();
    expect(() => validarPlan(plan({ cuadros: 11 }))).toThrow("incompleto");
    expect(() => validarPlan({ version: 1 })).toThrow("incompleto");
  });

  it("la dirección de la cámara es la de `render_view`: azimut en XY, elevación hacia Z", () => {
    const [x, y, z] = direccion(90, 0);
    expect(x).toBeCloseTo(0);
    expect(y).toBeCloseTo(1);
    expect(z).toBeCloseTo(0);
    expect(direccion(0, 90)[2]).toBeCloseTo(1);
    const d = direccion(-55, 22);
    expect(Math.hypot(...d)).toBeCloseTo(1);
  });

  it("el resaltado se apaga en resalte_s, como `linea_tiempo.resalte`", () => {
    expect(intensidadResalte(4, 4, 10, 1.2)).toBe(1);
    expect(intensidadResalte(10, 4, 10, 1.2)).toBeCloseTo(0.5);
    expect(intensidadResalte(16, 4, 10, 1.2)).toBe(0);
    expect(intensidadResalte(40, 4, 10, 1.2)).toBe(0);
  });

  it("la marcha sólo anda donde el plan lo dice y no se pasa del final de la serie", () => {
    const p = plan();
    expect(tiempoMarcha(p, 3, 5)).toBeNull();
    expect(tiempoMarcha(p, 7, 5)).toBeCloseTo(0.1);
    expect(tiempoMarcha(p, 9, 0.25)).toBe(0.25);
  });

  it("indexa las apariciones por cuadro", () => {
    expect(aparicionesPorCuadro(plan()).get(4)).toEqual(["b"]);
  });
});
