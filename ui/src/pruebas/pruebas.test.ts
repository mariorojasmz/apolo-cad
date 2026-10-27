import { describe, expect, it } from "vitest";
import { duracion, fechaCorta, progresoCorrida, textoIncidencia } from "./vista";

/* Lo que dice el panel «Pruebas» (plan visor-para-evaluar D3–D5). */

describe("fechaCorta", () => {
  const ahora = new Date(2026, 9, 26, 18, 0);
  it("hoy, ayer y otro día (con el año sólo si no es este)", () => {
    expect(fechaCorta("2026-10-26T14:03:09", ahora)).toBe("hoy, 14:03");
    expect(fechaCorta("2026-10-25T09:10:00", ahora)).toBe("ayer, 09:10");
    expect(fechaCorta("2026-10-02T07:05:00", ahora)).toBe("2 oct, 07:05");
    expect(fechaCorta("2025-12-31T23:59:00", ahora)).toBe("31 dic 2025, 23:59");
  });
  it("sin fecha o con una rota, nada", () => {
    expect(fechaCorta(undefined, ahora)).toBe("");
    expect(fechaCorta("ayer", ahora)).toBe("");
  });
});

describe("progreso de una corrida", () => {
  it("en la cola no hay fracción; corriendo, con lo que tardó la última vez", () => {
    expect(progresoCorrida({ jobId: "j", estado: "encolado", desde: null }, 0)).toEqual({
      frase: "En espera: otra prueba está corriendo", fraccion: null,
    });
    const c = { jobId: "j", estado: "corriendo" as const, desde: 0, estimadoS: 40 };
    expect(progresoCorrida(c, 10_000)).toEqual({ frase: "Corriendo · 10 s de unos 40 s", fraccion: 0.25 });
    expect(progresoCorrida(c, 90_000).fraccion).toBe(0.95); // nunca se completa sola
    expect(progresoCorrida({ ...c, estimadoS: undefined }, 5_000)).toEqual({ frase: "Corriendo · 5 s", fraccion: null });
  });
  it("duraciones legibles", () => {
    expect(duracion(9.6)).toBe("10 s");
    expect(duracion(100)).toBe("1 min 40 s");
    expect(duracion(600)).toBe("10 min");
  });
});

describe("textoIncidencia", () => {
  it("producto, qué le pasó, dónde (la pieza o el punto) y a qué hora", () => {
    expect(textoIncidencia({ tipo: "trabados", producto: "caja 3", que: "trabado", hora_s: 12.4, cerca_de: "Banda" }))
      .toBe("caja 3 trabado cerca de «Banda» a los 12 s");
    expect(textoIncidencia({ tipo: "perdidos", producto: "caja 1", que: "cayó al piso", hora_s: 3.25, punto_mm: [1200, -340, 0] }))
      .toBe("caja 1 cayó al piso en (1 200; −340; 0) mm a los 3,3 s");
    expect(textoIncidencia({ tipo: "trabados", mas: 4 })).toBe("y 4 más");
  });
});
