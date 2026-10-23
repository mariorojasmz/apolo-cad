import { describe, expect, it } from "vitest";
import { esperaDe, estadoDeMando } from "./accionar";
import { alApretar, alSoltar, colorFisico, encendido, girar, rotuloAccion } from "./mandos";
import type { MandoVivo } from "./protocolo";

/* Mando → mensaje del WebSocket (plan V8.4 D4): el pulsador vuelve al soltar, la seta queda
   retenida, el seccionador abre y cierra, el selector gira; y lo que el panel espera ver. */

const S1: MandoVivo = {
  designacion: "-S1", tipo: "pulsador", ref: "PULS-22-VERDE-NA", acciones: ["pulsar", "soltar", "girar"],
  color: "verde", retorno: "resorte", actuadores: ["mano"], potenciometro: false, senales: ["-S1.accionado"],
};
const S0: MandoVivo = {
  designacion: "-S0", tipo: "seta", ref: "ESTOP-40", acciones: ["presionar", "liberar"], color: "rojo",
  fondo: "amarillo", pieza: "c1271", senales: ["-S0.accionado"],
};
const Q1: MandoVivo = { designacion: "-Q1", tipo: "seccionador", ref: "SECC", acciones: ["abrir", "cerrar"], color: null, senales: ["-Q1.cerrado"] };
const S5: MandoVivo = { designacion: "-S5", tipo: "selector", ref: "SEL", acciones: ["girar"], color: "negro", posiciones: ["0", "I", "II"], senales: [] };
const S9: MandoVivo = { ...S1, designacion: "-S9", actuadores: ["marcha", "paro"], senales: ["-S9.marcha", "-S9.paro"] };

describe("mando → mensaje", () => {
  it("pulsador con resorte: bajar = pulsar sin durante_s, soltar = soltar", () => {
    expect(alApretar(S1)).toEqual({ accion: "pulsar", dispositivo: "-S1" });
    expect(alSoltar(S1)).toEqual({ accion: "soltar", dispositivo: "-S1" });
  });

  it("pulsador mantenido: alterna al bajar, al soltar no pasa nada", () => {
    const m = { ...S1, retorno: "mantenido" as const };
    expect(alApretar(m)).toEqual({ accion: "pulsar", dispositivo: "-S1" });
    expect(alSoltar(m)).toBeNull();
    expect(rotuloAccion(m)).toBe("Alternar");
  });

  it("pulsador doble: lleva su actuador", () => {
    expect(alApretar(S9, { actuador: "paro" })).toEqual({ accion: "pulsar", dispositivo: "-S9", actuador: "paro" });
    expect(alSoltar(S9, { actuador: "paro" })).toEqual({ accion: "soltar", dispositivo: "-S9", actuador: "paro" });
  });

  it("seta: presionar la retiene; otro clic la libera; soltar el mouse no la suelta", () => {
    expect(alApretar(S0, { retenida: false })).toEqual({ accion: "presionar", dispositivo: "-S0" });
    expect(alApretar(S0, { retenida: true })).toEqual({ accion: "liberar", dispositivo: "-S0" });
    expect(alSoltar(S0)).toBeNull();
    expect(rotuloAccion(S0, { retenida: true })).toBe("Liberar");
  });

  it("seccionador: abre si está cerrado, cierra si está abierto", () => {
    expect(alApretar(Q1, { cerrado: true })).toEqual({ accion: "abrir", dispositivo: "-Q1" });
    expect(alApretar(Q1, { cerrado: false })).toEqual({ accion: "cerrar", dispositivo: "-Q1" });
  });

  it("selector y potenciómetro: girar con su valor (el potenciómetro, entre 0 y 1)", () => {
    expect(girar(S5, "I")).toEqual({ accion: "girar", dispositivo: "-S5", valor: "I" });
    expect(girar(S1, 1.4)).toEqual({ accion: "girar", dispositivo: "-S1", valor: 1 });
    expect(alApretar(S5)).toBeNull();
  });
});

describe("estado del mando en el panel", () => {
  it("la señal manda; lo recién pedido va encima hasta que la señal lo muestre", () => {
    expect(estadoDeMando(S0, { lecturas: { "-S0.accionado": 0 }, esperadas: {} })).toEqual({ retenida: false });
    expect(estadoDeMando(S0, { lecturas: { "-S0.accionado": 0 }, esperadas: { "-S0.accionado": 1 } })).toEqual({ retenida: true });
    expect(estadoDeMando(Q1, { lecturas: { "-Q1.cerrado": 1 }, esperadas: {} })).toEqual({ cerrado: true });
    expect(estadoDeMando(Q1, { lecturas: {}, esperadas: {} })).toEqual({ cerrado: undefined });
  });

  it("qué valor se espera de cada acción", () => {
    expect(esperaDe({ accion: "presionar", dispositivo: "-S0" }, S0)).toEqual({ senal: "-S0.accionado", valor: 1 });
    expect(esperaDe({ accion: "soltar", dispositivo: "-S1" }, S1)).toEqual({ senal: "-S1.accionado", valor: 0 });
    expect(esperaDe({ accion: "abrir", dispositivo: "-Q1" }, Q1)).toEqual({ senal: "-Q1.cerrado", valor: 0 });
    expect(esperaDe({ accion: "girar", dispositivo: "-S5", valor: "I" }, S5)).toBeUndefined();
    expect(esperaDe({ accion: "pulsar", dispositivo: "-S9", actuador: "paro" }, S9)).toBeUndefined();
  });
});

describe("color físico y pilotos", () => {
  it("los colores del catálogo; sin color, null", () => {
    expect(colorFisico("verde")).toMatch(/^#/);
    expect(colorFisico("Ámbar")).toBe(colorFisico("ambar"));
    expect(colorFisico(null)).toBeNull();
    expect(colorFisico("fucsia")).toBeNull();
  });

  it("un piloto está encendido con su señal en 1", () => {
    expect(encendido(1)).toBe(true);
    expect(encendido(0)).toBe(false);
    expect(encendido(undefined)).toBe(false);
    expect(encendido(NaN)).toBe(false);
  });
});
