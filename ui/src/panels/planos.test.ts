import { describe, expect, it } from "vitest";
import { fraccion, fraseProgreso, textoEstimado } from "./planos";

/* Lo que dice el diálogo «Planos» mientras calcula (plan visor-para-evaluar D10–D12). */

describe("progreso del plano", () => {
  it("cuántas vistas están listas (corren a la vez), el corte solo y el armado al final", () => {
    expect(fraseProgreso({ hechas: 1, total: 4, fase: "planta" }, false)).toBe("Calculando las vistas · 1 de 4 listas");
    expect(fraseProgreso({ hechas: 0, total: 1, fase: "corte" }, false)).toBe("Calculando el corte");
    expect(fraseProgreso({ hechas: 4, total: 4, fase: "listo" }, false)).toBe("Armando la lámina");
    expect(fraseProgreso({ hechas: 11, total: 40, fase: "laminas" }, false)).toBe("Lámina 12 de 40");
    expect(fraseProgreso(undefined, true)).toBe("En espera: otro plano se está armando");
    expect(fraseProgreso(undefined, false)).toBe("Empezando…");
  });
  it("la fracción y el estimado", () => {
    expect(fraccion({ hechas: 1, total: 4, fase: "planta" })).toBe(0.25);
    expect(fraccion(undefined)).toBeNull();
    expect(textoEstimado(280)).toBe("unos 5 min");
    expect(textoEstimado(42)).toBe("unos 40 s");
    expect(textoEstimado(undefined)).toBe("");
  });
});
