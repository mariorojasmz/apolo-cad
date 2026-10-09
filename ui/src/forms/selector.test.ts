import { describe, expect, it } from "vitest";
import { normalizeSelector, seleccionDelClic } from "./selector";

describe("selector de caras y aristas", () => {
  it("el clic guarda una selección nueva que mide a la superficie", () => {
    const punto: [number, number, number] = [128, 50, 6];
    const sel = seleccionDelClic(punto, null);
    expect(sel).toEqual({ mode: "cerca", point: [128, 50, 6], count: 1, medir: "superficie" });
    expect(sel.point).not.toBe(punto); // copia: el arreglo del viewport no queda compartido
  });

  it("el clic conserva cuántas y la entidad de la selección anterior", () => {
    const prev = { mode: "cara", face: "tope", count: 2, entidad: "arista" };
    expect(seleccionDelClic([1, 2, 3], prev)).toEqual({
      mode: "cerca", point: [1, 2, 3], count: 2, medir: "superficie", entidad: "arista",
    });
  });

  it("una selección guardada sin medir se reenvía igual, sin la clave", () => {
    const vieja = { mode: "cerca", point: [3806, 391.5, 811], count: 1 };
    const out = normalizeSelector(vieja);
    expect(out).toEqual(vieja);
    expect("medir" in out).toBe(false);
    expect(JSON.stringify(out)).toBe(JSON.stringify(vieja));
  });

  it("conserva medir en cerca y lo descarta en los otros modos", () => {
    expect(normalizeSelector({ mode: "cerca", point: [0, 0, 0], medir: "superficie" }).medir).toBe("superficie");
    expect(normalizeSelector({ mode: "cerca", point: [0, 0, 0], medir: "centro" }).medir).toBe("centro");
    expect("medir" in normalizeSelector({ mode: "cara", face: "base", medir: "superficie" })).toBe(false);
  });
});
