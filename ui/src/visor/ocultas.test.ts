import { describe, expect, it } from "vitest";
import type { FeatureOut } from "../types";
import { avisoOcultas } from "./ocultas";

const f = (id: string, visible: boolean): FeatureOut =>
  ({ id, name: `Pieza ${id}`, visible } as unknown as FeatureOut);

describe("aviso de piezas ocultas", () => {
  it("sin ocultas no hay aviso", () => {
    expect(avisoOcultas([f("a", true), f("b", true)])).toEqual({ texto: null, sola: null });
    expect(avisoOcultas([])).toEqual({ texto: null, sola: null });
  });
  it("cuenta en singular y plural", () => {
    expect(avisoOcultas([f("a", false), f("b", true), f("c", true)]).texto).toBe("1 pieza oculta");
    expect(avisoOcultas([f("a", false), f("b", false), f("c", true), f("d", true)]).texto).toBe("2 piezas ocultas");
  });
  it("con una sola a la vista (Aislar), la nombra", () => {
    expect(avisoOcultas([f("a", false), f("b", false), f("c", true)])).toEqual({ texto: "Solo se ve", sola: "Pieza c" });
  });
  it("todas ocultas: cuenta", () => {
    expect(avisoOcultas([f("a", false), f("b", false)]).texto).toBe("2 piezas ocultas");
  });
});
