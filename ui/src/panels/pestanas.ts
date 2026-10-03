import type { CommandSchema } from "../types";

/* Las pestañas del ribbon salen del servidor (`pestana` de cada comando en la vista
   persona, fuente única en `core/apolo/commands/pistas.py::PESTANAS`), no de una lista
   escrita a mano: con la lista a mano, una categoría nueva desaparecía en silencio (pasó
   con las superficies). Función pura: el ribbon sólo la pinta. */

export interface PestanaRibbon {
  /** La categoría del registro («superficies»). */
  clave: string;
  /** El nombre que se lee («Superficies»). */
  rotulo: string;
  orden: number;
  /** Sus comandos, en el orden en que llegan del servidor. */
  comandos: CommandSchema[];
}

/** Una pestaña por categoría con pestaña (`pestana` no nula) y al menos un comando,
 *  ordenadas por `orden`. */
export function pestanasDe(schemas: CommandSchema[]): PestanaRibbon[] {
  const porCategoria = new Map<string, PestanaRibbon>();
  for (const s of schemas) {
    if (!s.pestana) continue;
    let p = porCategoria.get(s.category);
    if (!p) {
      p = { clave: s.category, rotulo: s.pestana.rotulo, orden: s.pestana.orden, comandos: [] };
      porCategoria.set(s.category, p);
    }
    p.comandos.push(s);
  }
  return [...porCategoria.values()].sort((a, b) => a.orden - b.orden);
}
