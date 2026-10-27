import { describe, expect, it } from "vitest";
import { esperaDe, estadoDeMando } from "./accionar";
import { readFileSync } from "node:fs";
import { ACABADO_DE_COLOR, ACABADOS } from "../viewport/acabados";
import type { ZonaOut } from "../types";
import { alApretar, alSoltar, colorFisico, EMISION_PILOTO, encendido, girar, llevarA, materialesQueBrillan,
  rotuloAccion, tonoEncendido } from "./mandos";
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
const B2: MandoVivo = { designacion: "-B2", tipo: "resguardo", ref: "RESG-2NC", acciones: ["abrir", "cerrar"], color: null, senales: ["-B2.cerrado"] };
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

  it("resguardo: se abre y se cierra como el seccionador y se lee su estado (mandos-de-seguridad D2)", () => {
    expect(alApretar(B2, { cerrado: true })).toEqual({ accion: "abrir", dispositivo: "-B2" });
    expect(alApretar(B2, { cerrado: false })).toEqual({ accion: "cerrar", dispositivo: "-B2" });
    expect(alSoltar(B2)).toBeNull();
    expect(rotuloAccion(B2, { cerrado: true })).toBe("Abrir");
    expect(rotuloAccion(B2, { cerrado: false })).toBe("Cerrar");
    expect(rotuloAccion(S1)).toBe("Presionar"); // un solo verbo para apretar un mando
    expect(estadoDeMando(B2, { lecturas: { "-B2.cerrado": 0 }, esperadas: {} })).toEqual({ cerrado: false });
    expect(esperaDe({ accion: "cerrar", dispositivo: "-B2" }, B2)).toEqual({ senal: "-B2.cerrado", valor: 1 });
  });

  it("selector y potenciómetro: girar con su valor (el potenciómetro, entre 0 y 1)", () => {
    expect(girar(S5, "I")).toEqual({ accion: "girar", dispositivo: "-S5", valor: "I" });
    expect(girar(S1, 1.4)).toEqual({ accion: "girar", dispositivo: "-S1", valor: 1 });
    expect(alApretar(S5)).toBeNull();
  });

  it("un segmento lleva el mando a ese estado: cerrar/abrir o girar (nombres-por-funcion D9)", () => {
    expect(llevarA(Q1, "abierto")).toEqual({ accion: "abrir", dispositivo: "-Q1" });
    expect(llevarA(B2, "cerrado")).toEqual({ accion: "cerrar", dispositivo: "-B2" });
    expect(llevarA(S5, "II")).toEqual({ accion: "girar", dispositivo: "-S5", valor: "II" });
  });

  it("la UI no guarda nombres de tipo de mando (los da el servidor, D13)", () => {
    const fuente = readFileSync(new URL("./mandos.ts", import.meta.url), "utf8");
    expect(fuente).not.toMatch(/Seta de emergencia|"Seccionador"|"Resguardo"|"Selector"/);
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

  it("el color físico es el albedo del acabado de su color: una sola tabla de tonos", () => {
    expect(colorFisico("verde")).toBe(ACABADOS.plastico_verde.color);
    expect(colorFisico("rojo")).toBe(ACABADOS.plastico_rojo_seguridad.color);
    expect(colorFisico(" Ámbar ")).toBe(ACABADOS.plastico_ambar.color);
    expect(colorFisico("amarillo")).toBe(ACABADOS.plastico_amarillo_seguridad.color); // el fondo de la seta
    for (const [nombre, acabado] of Object.entries(ACABADO_DE_COLOR)) {
      expect(colorFisico(nombre), nombre).toBe(ACABADOS[acabado].color);
    }
    // un color sin acabado no tiene tono inventado
    expect(colorFisico("naranja")).toBeNull();
  });

  it("mandos.ts no guarda tonos propios (ni un #rrggbb)", () => {
    const fuente = readFileSync(new URL("./mandos.ts", import.meta.url), "utf8");
    expect(fuente.match(/#[0-9a-f]{3,8}\b/gi) ?? []).toEqual([]);
  });

  it("el piloto encendido brilla en el tono de su acabado; sin color, en el blanco", () => {
    expect(tonoEncendido("verde")).toBe(ACABADOS.plastico_verde.color);
    expect(tonoEncendido(null)).toBe(ACABADOS.plastico_blanco.color);
    expect(tonoEncendido("fucsia")).toBe(ACABADOS.plastico_blanco.color);
    expect(EMISION_PILOTO).toBeGreaterThan(0);
  });

  it("sólo la zona de color se enciende; sin zonas de color, la pieza entera", () => {
    const z = (zona: string, de_color?: boolean): ZonaOut => ({
      acabado: "plastico_negro", albedo: "#000000", desde: 0, hasta: 1, zona, ...(de_color ? { de_color } : {}),
    });
    expect(materialesQueBrillan([z("frente", true), z("bisel"), z("cuerpo")], 3)).toEqual([0]);
    expect(materialesQueBrillan([z("bisel"), z("frente", true), z("cuerpo")], 3)).toEqual([1]);
    // servidor anterior (sin `de_color`), sin zonas o con otra partición: todo, como antes
    expect(materialesQueBrillan([z("frente"), z("bisel"), z("cuerpo")], 3)).toEqual([0, 1, 2]);
    expect(materialesQueBrillan(undefined, 1)).toEqual([0]);
    expect(materialesQueBrillan([z("frente", true), z("bisel")], 1)).toEqual([0]);
  });

  it("un piloto está encendido con su señal en 1", () => {
    expect(encendido(1)).toBe(true);
    expect(encendido(0)).toBe(false);
    expect(encendido(undefined)).toBe(false);
    expect(encendido(NaN)).toBe(false);
  });
});
