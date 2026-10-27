import type { ConNombre } from "../diseno/nombres";

/* ¿La pieza elegida es un aparato? (plan nombres-por-funcion F4): la ficha de pieza suma una línea
   «Marcha · -S1» con lo que la UI YA leyó del servidor, sin pedir nada nuevo: la tabla del `inicio`
   de la sesión viva (mandos, pilotos, dispositivos y válvulas, con su `pieza` 3D), los aparatos del
   panel «Tablero» y los de «Neumática» (sus piezas en el esquema, sus nombres por designación). Si
   ninguna está a mano, no hay línea: la ficha no pide un dato que no tiene. Puro. */

/** Un aparato con la pieza 3D que lo dibuja. */
export interface AparatoConPieza extends ConNombre {
  pieza?: string;
  /** Otras piezas del mismo aparato (el cuerpo y el vástago de un cilindro). */
  piezas?: readonly string[];
}

/** El aparato que dibuja la pieza `id`, buscado en el orden de las fuentes; null si ninguno. */
export function aparatoDePieza(id: string, fuentes: readonly (readonly AparatoConPieza[] | null | undefined)[]): ConNombre | null {
  for (const lista of fuentes) {
    const a = lista?.find((x) => x.pieza === id || x.piezas?.includes(id));
    if (a) return a.rotulo ? { designacion: a.designacion, rotulo: a.rotulo } : { designacion: a.designacion };
  }
  return null;
}

/** Los aparatos de «Neumática» con sus piezas: los símbolos del esquema con el nombre de `nombres`. */
export function aparatosDeNeumatica(
  simbolos: readonly { designacion: string; piezas: readonly string[] }[] | undefined,
  nombres: Record<string, { rotulo?: string }> | undefined,
): AparatoConPieza[] {
  return (simbolos ?? []).map((s) => ({ designacion: s.designacion, piezas: s.piezas, rotulo: nombres?.[s.designacion]?.rotulo }));
}
