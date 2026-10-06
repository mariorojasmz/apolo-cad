import { afterEach, describe, expect, it, vi } from "vitest";
import { copiarAlPortapapeles, referenciaParaAgente } from "./copiar";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("copiar para el agente", () => {
  it("copia el nombre entre comillas latinas y el id entre paréntesis", () => {
    expect(referenciaParaAgente("Larguero (+Y)", "c45_2")).toBe("«Larguero (+Y)» (c45_2)");
  });

  it("avisa true cuando el portapapeles acepta", async () => {
    const writeText = vi.fn(async () => {});
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    expect(await copiarAlPortapapeles("«A» (c1)")).toBe(true);
    expect(writeText).toHaveBeenCalledWith("«A» (c1)");
  });

  it("avisa false sin portapapeles o si lo niega, sin lanzar", async () => {
    vi.stubGlobal("navigator", {});
    expect(await copiarAlPortapapeles("x")).toBe(false);
    vi.stubGlobal("navigator", { clipboard: { writeText: async () => Promise.reject(new Error("NotAllowedError")) } });
    expect(await copiarAlPortapapeles("x")).toBe(false);
  });
});
