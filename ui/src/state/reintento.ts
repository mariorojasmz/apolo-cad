/* Reintento de las llamadas de la sincronización de fondo (`pumpEdit` y `enqueueSilent` de
   `store.ts`). Salió de la store para hacerle lugar bajo su trinquete de tamaño (plan
   modo-visor, D12). Sin dependencias: se prueba sola. */

/** Corre `run`; si falla (red caída, servidor ocupado) espera `delayMs` y reintenta hasta
   `tries` veces más. Agotados los reintentos, propaga el ÚLTIMO error. */
export async function withRetry<T>(run: () => Promise<T>, tries = 2, delayMs = 350): Promise<T> {
  try {
    return await run();
  } catch (e) {
    if (tries > 0) { await new Promise((r) => setTimeout(r, delayMs)); return withRetry(run, tries - 1, delayMs); }
    throw e;
  }
}
