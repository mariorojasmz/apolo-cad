import type { DocumentOut } from "../types";

/* Lógica pura de Deshacer y Rehacer con su lista de cambios (plan deshacer-con-etiqueta, D7 y
   D8), sin React ni store, para probarla aislada. Un paso del historial se llama «cambio» (puede
   ser un lote de muchos comandos). Las etiquetas llegan del servidor ya escritas para la persona,
   la más próxima primero; aquí sólo se les antepone el verbo. El componente es
   `HistorialCambios.tsx` (`historialCambios.ts` chocaría con él: Windows no distingue mayúsculas). */

export type Sentido = "deshacer" | "rehacer";

const VERBO: Record<Sentido, string> = { deshacer: "Deshacer", rehacer: "Rehacer" };

type DocHistorial = Pick<DocumentOut, "can_undo" | "can_redo" | "undo_labels" | "redo_labels">;

/** Las etiquetas del sentido pedido, la más próxima primero; vacía si la API no las manda. */
export function etiquetasDe(doc: DocHistorial | undefined, sentido: Sentido): string[] {
  const lista = sentido === "deshacer" ? doc?.undo_labels : doc?.redo_labels;
  return Array.isArray(lista) ? lista : [];
}

/** Hay algo para deshacer (o para rehacer). */
export function hayCambios(doc: DocHistorial | undefined, sentido: Sentido): boolean {
  return !!(sentido === "deshacer" ? doc?.can_undo : doc?.can_redo);
}

/** `title` y `aria-label` del botón: el verbo y el próximo cambio; sin etiqueta, el verbo solo. */
export function tituloBoton(sentido: Sentido, etiquetas: readonly string[]): string {
  const proximo = etiquetas[0]?.trim();
  return proximo ? `${VERBO[sentido]}: ${proximo}` : VERBO[sentido];
}

/** El pie de la lista: cuántos cambios revierte el clic en la fila marcada. */
export function textoPie(sentido: Sentido, k: number): string {
  return `${VERBO[sentido]} ${k} ${k === 1 ? "cambio" : "cambios"}`;
}

/** `aria-label` del botón ▾ que abre la lista. */
export const rotuloAbrir = (sentido: Sentido) => `Ver los cambios para ${sentido}`;

/** `aria-label` de la lista. */
export const rotuloLista = (sentido: Sentido) => `Cambios para ${sentido}`;

/** Qué fila enfocar al apretar `tecla` estando en la fila `actual` de `n`, o `null` si la tecla
   no mueve el foco de la lista. Sin vuelta: en la primera, la flecha arriba se queda ahí. */
export function filaConTecla(actual: number, tecla: string, n: number): number | null {
  if (n <= 0) return null;
  switch (tecla) {
    case "ArrowDown": return Math.min(actual + 1, n - 1);
    case "ArrowUp": return Math.max(actual - 1, 0);
    case "Home": return 0;
    case "End": return n - 1;
    default: return null;
  }
}
