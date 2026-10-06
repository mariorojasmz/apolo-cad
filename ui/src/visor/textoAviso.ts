import type { CambiosAgente } from "./estado";

/* Texto del aviso de los cambios del agente (plan modo-visor, D8). Puro: lo prueba
   `textoAviso.test.ts` y lo pinta `AvisoAgente.tsx`. */

const piezas = (n: number) => `${n} ${n === 1 ? "pieza" : "piezas"}`;

/** «El agente agregó 2 piezas», «El agente cambió 1 pieza», «El agente eliminó 3 piezas» o
   la mezcla: «El agente agregó 1 pieza, cambió 2 y eliminó 1» (el sustantivo va sólo en la
   primera cuenta). Vacío si no hay nada que contar. */
export function textoAviso(c: CambiosAgente): string {
  const partes: string[] = [];
  const cuenta = (n: number) => (partes.length ? String(n) : piezas(n));
  if (c.nuevos.length) partes.push(`agregó ${cuenta(c.nuevos.length)}`);
  if (c.cambiados.length) partes.push(`cambió ${cuenta(c.cambiados.length)}`);
  if (c.eliminados > 0) partes.push(`eliminó ${cuenta(c.eliminados)}`);
  if (!partes.length) return "";
  const ultima = partes.pop()!;
  return `El agente ${partes.length ? `${partes.join(", ")} y ${ultima}` : ultima}`;
}
