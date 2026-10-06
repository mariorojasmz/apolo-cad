/* Lógica pura de los cajones del visor (plan modo-visor, D3): qué cierra Esc y qué paneles van
   en el menú «Más» de la barra. Sin React ni DOM real, para probarla con vitest. */

export type Lado = "izq" | "der";

/** Atributo de un elemento flotante que se cierra con Esc ANTES que los cajones (el menú
   «Más» de la barra de paneles). */
export const CIERRA_CON_ESC = "data-cierra-con-esc";

export interface Cajones {
  cajonIzq: boolean;
  cajonDer: string | null;
}

/** Qué cajón cierra Esc: el derecho primero, después el izquierdo. Ninguno si Esc tiene antes
   otra cosa que cerrar (`prioridad`: diálogo, menú contextual, pedido de punto, ayuda) o si se
   tecleó dentro de un campo de texto (`enCampo`: ahí Esc es del campo). */
export function cajonQueCierraEsc(c: Cajones, o: { prioridad: boolean; enCampo: boolean }): Lado | null {
  if (o.prioridad || o.enCampo) return null;
  if (c.cajonDer) return "der";
  if (c.cajonIzq) return "izq";
  return null;
}

/** El foco está en algo donde se escribe (input, textarea, select o contenido editable). */
export function esCampoDeTexto(t: { tagName?: string; isContentEditable?: boolean } | null): boolean {
  if (!t) return false;
  return !!t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName ?? "");
}

/** Paneles del menú «Más»: las herramientas que no tienen botón propio en la barra, en su orden.
   Un panel-herramienta nuevo aparece aquí solo. */
export function panelesDelMenu<T extends string>(herramientas: readonly T[], conBoton: readonly string[]): T[] {
  return herramientas.filter((id) => !conBoton.includes(id));
}
