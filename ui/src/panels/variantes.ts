import type { VariableOut } from "../types";

/* Lógica pura de la tabla de variantes (sin React ni store, para probarla aislada). Una
   variante guarda SÓLO las variables de su tabla y todas tienen las mismas: las filas son la
   unión de las claves de `configuration_values`. Lo que cambiaría al aplicar se calcula
   contra la expresión vigente de cada variable, sin pedirle nada al servidor. */

/** Misma expresión, sin contar espacios de los bordes. */
export const mismaExpresion = (a: string | undefined, b: string | undefined) =>
  (a ?? "").trim() === (b ?? "").trim();

export interface TablaVariantes {
  /** Las variables de la tabla, en orden alfabético. */
  filas: string[];
  /** Expresión vigente de cada variable del proyecto. */
  actual: Map<string, string>;
  /** Variables del proyecto que no están en la tabla (lo que se puede agregar). */
  fuera: string[];
  /** La celda difiere del modelo: aplicar esa variante la cambiaría. */
  difiere: (variante: string, variable: string) => boolean;
  /** La variante coincide entera con el modelo (aplicarla no cambiaría nada). */
  coincide: (variante: string) => boolean;
}

export function tablaDeVariantes(
  variables: VariableOut[],
  configurations: string[],
  valores: Record<string, Record<string, string>>,
): TablaVariantes {
  const actual = new Map(variables.map((v) => [v.name, v.expression]));
  const filas = [...new Set(configurations.flatMap((c) => Object.keys(valores[c] ?? {})))].sort((a, b) =>
    a.localeCompare(b),
  );
  // Una fila cuya variable ya no existe no cuenta: aplicar la ignora (y el servidor avisa).
  const vivas = filas.filter((v) => actual.has(v));
  const difiere = (c: string, v: string) => actual.has(v) && !mismaExpresion(valores[c]?.[v], actual.get(v));
  return {
    filas,
    actual,
    fuera: variables.map((v) => v.name).filter((n) => !filas.includes(n)),
    difiere,
    coincide: (c) => vivas.length > 0 && vivas.every((v) => !difiere(c, v)),
  };
}

/** Por qué «Crear variante» está deshabilitado, o `null` si se puede crear. La primera
 *  variante (tabla sin filas) necesita además la variable que la distingue. */
export function motivoParaCrear(o: {
  hayVariables: boolean;
  pideVariable: boolean;
  nombre: string;
  distingue: string;
}): string | null {
  const sinNombre = !o.nombre.trim();
  const sinVariable = o.pideVariable && !o.distingue;
  if (!o.hayVariables) return "Crea primero una variable arriba.";
  if (sinNombre && sinVariable) return "Escribe el nombre y elige la variable que distingue a esta variante.";
  if (sinVariable) return "Elige la variable que distingue a esta variante.";
  if (sinNombre) return "Escribe el nombre de la variante.";
  return null;
}
