import { describe, expect, it } from "vitest";
import type { VariableOut } from "../types";
import { motivoParaCrear, tablaDeVariantes } from "./variantes";

/* La tabla de variantes muestra SÓLO las variables de su tabla (no todas las del proyecto) y
   marca, sin pedirle nada al servidor, qué cambiaría al aplicar cada variante. El caso es el
   del proyecto 38: dos variantes que difieren sólo en largo_total. */

const variable = (name: string, expression: string): VariableOut => ({
  name,
  expression,
  value: Number(expression) || null,
  command_id: `var_${name}`,
});

const VARIABLES = [variable("largo_total", "4000"), variable("ancho", "600"), variable("sec_pata", "sec_larg_h")];
const VARIANTES = ["3.2m", "4m estandar"];
const VALORES = { "3.2m": { largo_total: "3200" }, "4m estandar": { largo_total: " 4000 " } };

describe("tablaDeVariantes", () => {
  it("las filas son sólo las variables de la tabla, no todas las del proyecto", () => {
    const t = tablaDeVariantes(VARIABLES, VARIANTES, VALORES);
    expect(t.filas).toEqual(["largo_total"]);
    expect(t.fuera).toEqual(["ancho", "sec_pata"]);
  });

  it("resalta la celda que cambiaría y marca la variante que ya coincide con el modelo", () => {
    const t = tablaDeVariantes(VARIABLES, VARIANTES, VALORES);
    expect(t.difiere("3.2m", "largo_total")).toBe(true);
    expect(t.difiere("4m estandar", "largo_total")).toBe(false); // los espacios no cuentan
    expect(t.coincide("3.2m")).toBe(false);
    expect(t.coincide("4m estandar")).toBe(true);
  });

  it("las filas se ordenan y salen de todas las variantes", () => {
    const t = tablaDeVariantes(VARIABLES, ["a", "b"], { a: { largo_total: "1", ancho: "2" }, b: {} });
    expect(t.filas).toEqual(["ancho", "largo_total"]);
  });

  it("una fila de una variable eliminada no se resalta ni impide la marca «actual»", () => {
    const valores = { "4m estandar": { largo_total: "4000", n_patas: "3" } };
    const t = tablaDeVariantes(VARIABLES, ["4m estandar"], valores);
    expect(t.filas).toEqual(["largo_total", "n_patas"]);
    expect(t.difiere("4m estandar", "n_patas")).toBe(false);
    expect(t.coincide("4m estandar")).toBe(true);
  });

  it("sin filas no hay variante «actual» (no hay nada que comparar)", () => {
    const t = tablaDeVariantes(VARIABLES, ["vacia"], { vacia: {} });
    expect(t.filas).toEqual([]);
    expect(t.coincide("vacia")).toBe(false);
  });
});

describe("motivoParaCrear", () => {
  const base = { hayVariables: true, pideVariable: false, nombre: "3 metros", distingue: "" };

  it("con filas en la tabla basta el nombre", () => {
    expect(motivoParaCrear(base)).toBeNull();
    expect(motivoParaCrear({ ...base, nombre: "  " })).toBe("Escribe el nombre de la variante.");
  });

  it("la primera variante pide además la variable que la distingue", () => {
    const primera = { ...base, pideVariable: true };
    expect(motivoParaCrear(primera)).toBe("Elige la variable que distingue a esta variante.");
    expect(motivoParaCrear({ ...primera, nombre: "" })).toMatch(/nombre y elige la variable/);
    expect(motivoParaCrear({ ...primera, distingue: "largo_total" })).toBeNull();
  });

  it("sin variables en el proyecto no hay variante posible", () => {
    expect(motivoParaCrear({ ...base, hayVariables: false })).toBe("Crea primero una variable arriba.");
  });
});
