import type { CambiosAgente } from "./estado";

/* Texto del aviso del agente (plan modo-visor): los cambios (D8) y el «trabajando» en vivo
   (D10). Puro: lo prueba `textoAviso.test.ts` y lo pinta `AvisoAgente.tsx`. */

/** El aviso en curso mientras corre un lote del agente. */
export const TEXTO_TRABAJANDO = "El agente está trabajando…";

/** Lo que pinta el aviso: el «trabajando» (con spinner, sin botones) o los cambios. */
export type AvisoVisible = { tipo: "trabajando"; texto: string } | { tipo: "cambios"; texto: string };

/** Qué aviso va: mientras el agente trabaja, «trabajando» gana a un aviso de cambios viejo;
   si no, el de cambios, o ninguno si no hay nada que contar. */
export function avisoVisible(trabajando: boolean, aviso: CambiosAgente | null): AvisoVisible | null {
  if (trabajando) return { tipo: "trabajando", texto: TEXTO_TRABAJANDO };
  const texto = aviso ? textoAviso(aviso) : "";
  return texto ? { tipo: "cambios", texto } : null;
}

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
