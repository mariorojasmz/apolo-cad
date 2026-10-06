/* «Copiar para el agente» (plan modo-visor, D6 y D7): la persona le habla al agente por fuera
   de la app y el agente ubica la pieza por su id. Lo usan la barra de selección del visor y,
   desde F3, la ficha de pieza. */

/** Lo que se copia: el nombre que ve la persona y el id que usa el agente. */
export const referenciaParaAgente = (nombre: string, id: string): string => `«${nombre}» (${id})`;

/** Copia al portapapeles; false si no se pudo (sin contexto seguro `clipboard` no existe, o el
   navegador negó el permiso) para que quien llama muestre el texto y se copie a mano. */
export async function copiarAlPortapapeles(texto: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch {
    return false;
  }
}
