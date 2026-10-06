import { describe, expect, it } from "vitest";
import { CacheMasa, SIN_DATO, formatearMedidas, formatearPeso, nombreMaterial } from "./ficha";

describe("medidas de la ficha", () => {
  it("escribe X × Y × Z desde el bbox, con un decimal como mucho", () => {
    const larguero = { min: [-2000, -50.8, 0], max: [2000, 50.8, 50.8] };
    expect(formatearMedidas(larguero)).toBe("4000 × 101.6 × 50.8 mm");
  });

  it("limpia el ruido de coma flotante", () => {
    expect(formatearMedidas({ min: [0, 0, 0], max: [101.60000001, 9.999999, 0.04] })).toBe("101.6 × 10 × 0 mm");
  });

  it("una caja vacía o rota no inventa medidas", () => {
    expect(formatearMedidas({ min: [Infinity, 0, 0], max: [-Infinity, 1, 1] })).toBe(SIN_DATO);
    expect(formatearMedidas({ min: [], max: [] })).toBe(SIN_DATO);
  });
});

describe("peso de la ficha", () => {
  it("usa los decimales que dicen algo", () => {
    expect(formatearPeso(123.456)).toBe("123.5 kg");
    expect(formatearPeso(2.5864)).toBe("2.59 kg");
    expect(formatearPeso(0.0123)).toBe("0.012 kg");
    expect(formatearPeso(0)).toBe("0 kg");
  });

  it("un peso inválido se muestra como «—»", () => {
    expect(formatearPeso(NaN)).toBe(SIN_DATO);
    expect(formatearPeso(-1)).toBe(SIN_DATO);
  });
});

describe("material de la ficha", () => {
  it("pone la mayúscula y las tildes que la clave del servidor no trae", () => {
    expect(nombreMaterial("acero")).toBe("Acero");
    expect(nombreMaterial("acero inoxidable")).toBe("Acero inoxidable");
    expect(nombreMaterial("laton")).toBe("Latón");
    expect(nombreMaterial("pvc")).toBe("PVC");
    expect(nombreMaterial("  ")).toBe(SIN_DATO);
  });
});

describe("caché de la masa", () => {
  it("guarda por id + rev dentro de una versión del documento", () => {
    const c = new CacheMasa<number>();
    const doc = {};
    expect(c.leer(doc, "c1", 1)).toBeUndefined();
    c.guardar(doc, "c1", 1, 2.5);
    expect(c.leer(doc, "c1", 1)).toBe(2.5);
    expect(c.leer(doc, "c1", 2)).toBeUndefined(); // geometría nueva: se vuelve a pedir
    expect(c.leer(doc, "c2", 1)).toBeUndefined();
  });

  it("otra versión del documento la vacía (el material cambia sin subir el rev)", () => {
    const c = new CacheMasa<number>();
    const v1 = {};
    const v2 = {};
    c.leer(v1, "c1", 1);
    c.guardar(v1, "c1", 1, 2.5);
    expect(c.leer(v2, "c1", 1)).toBeUndefined();
  });

  it("una respuesta tardía de una versión vieja no se guarda", () => {
    const c = new CacheMasa<number>();
    const v1 = {};
    const v2 = {};
    c.leer(v1, "c1", 1);
    c.leer(v2, "c1", 1); // llegó otra escena mientras se pedía
    c.guardar(v1, "c1", 1, 2.5);
    expect(c.leer(v2, "c1", 1)).toBeUndefined();
    c.guardar(v2, "c1", 1, 3);
    expect(c.leer(v2, "c1", 1)).toBe(3);
  });
});
