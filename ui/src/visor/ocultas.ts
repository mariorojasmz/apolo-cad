import type { FeatureOut } from "../types";

/* Texto del aviso de piezas ocultas del visor. En Completo el árbol muestra cada ojo; en el
   visor no hay árbol a la vista, así que sin este aviso una pieza oculta (Ocultar, Aislar)
   desaparece sin rastro y no hay por dónde volver. */

export interface AvisoOcultas {
  /** Lo que dice el aviso; null = no hay piezas ocultas. */
  texto: string | null;
  /** La única pieza a la vista cuando se aisló una (para nombrarla). */
  sola: string | null;
}

export function avisoOcultas(features: readonly FeatureOut[]): AvisoOcultas {
  const ocultas = features.filter((f) => !f.visible).length;
  if (!ocultas) return { texto: null, sola: null };
  const visibles = features.filter((f) => f.visible);
  if (visibles.length === 1) return { texto: "Solo se ve", sola: visibles[0].name };
  return { texto: `${ocultas} ${ocultas === 1 ? "pieza oculta" : "piezas ocultas"}`, sola: null };
}
