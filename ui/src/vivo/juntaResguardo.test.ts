import { describe, expect, it } from "vitest";
import { crearJuntasDeResguardo, valorDeJunta } from "./juntaResguardo";
import type { MandoVivo } from "./protocolo";

/* «Puerta abierta» abre la puerta (plan lo-que-se-mueve, D4): el mando de un resguardo con junta
   lleva su hoja a `abierto` al abrir y a `cerrado` al cerrar; sin junta, no mueve nada. */

const base: MandoVivo = {
  designacion: "-B11", tipo: "resguardo", ref: "RESG-2NC", acciones: ["abrir", "cerrar"],
  color: null, senales: ["-B11.cerrado"],
};
const conJunta: MandoVivo = { ...base, junta: "j_puerta", abierto: 95, cerrado: 0 };

function visor(inicial: Record<string, number> = {}) {
  const valores: Record<string, number> = { ...inicial };
  const llamadas: [string, number][] = [];
  return {
    valores, llamadas,
    leer: (j: string) => valores[j] ?? 0,
    poner: (j: string, v: number) => { llamadas.push([j, v]); valores[j] = v; },
  };
}

describe("la junta del resguardo en el visor", () => {
  it("abrir la lleva a upper y cerrar a lower", () => {
    const v = visor();
    const juntas = crearJuntasDeResguardo(v);
    expect(juntas.mover({ accion: "abrir", dispositivo: "-B11" }, conJunta)).toBe(true);
    expect(juntas.mover({ accion: "cerrar", dispositivo: "-B11" }, conJunta)).toBe(true);
    expect(v.llamadas).toEqual([["j_puerta", 95], ["j_puerta", 0]]);
  });

  it("sin junta no la llama: el resguardo muestra su estado como siempre", () => {
    const v = visor();
    const juntas = crearJuntasDeResguardo(v);
    expect(juntas.mover({ accion: "abrir", dispositivo: "-B11" }, base)).toBe(false);
    expect(juntas.mover({ accion: "cerrar", dispositivo: "-B11" }, base)).toBe(false);
    expect(v.llamadas).toEqual([]);
  });

  it("otro mando u otra acción no la mueven", () => {
    expect(valorDeJunta({ accion: "pulsar", dispositivo: "-B11" }, conJunta)).toBeNull(); // voseo-interno
    expect(valorDeJunta({ accion: "abrir", dispositivo: "-Q1" }, { ...conJunta, tipo: "seccionador" })).toBeNull();
  });

  it("al cerrar la sesión, la junta vuelve al valor que tenía", () => {
    const v = visor({ j_puerta: 10 });
    const juntas = crearJuntasDeResguardo(v);
    juntas.mover({ accion: "abrir", dispositivo: "-B11" }, conJunta);
    juntas.mover({ accion: "cerrar", dispositivo: "-B11" }, conJunta);
    juntas.mover({ accion: "abrir", dispositivo: "-B11" }, conJunta);
    juntas.devolver();
    expect(v.valores.j_puerta).toBe(10);
    juntas.devolver(); // ya no recuerda nada: no vuelve a tocarla
    expect(v.llamadas.length).toBe(4);
  });
});
