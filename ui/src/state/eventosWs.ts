/* Avisos de jobs que llegan por el WebSocket (plan modo-visor, D10). `connectWs` (api.ts) los
   publica en `window` como eventos y el visor los escucha (`visor/trabajando.ts`): ni el
   transporte ni la store conocen al visor, el mismo patrón desacoplado que
   `apolo:cambios-externos`. Puro salvo el despacho, que recibe su destino. */

/** Evento de `window` por cada aviso de job válido; su `detail` es un `AvisoJob`. */
export const EVENTO_JOB = "apolo:job";
/** Evento de `window` cuando el WS se RECONECTA (no en la primera conexión): los avisos que
   se perdieron mientras estuvo caído dejarían un «trabajando» colgado. Sin `detail`. */
export const EVENTO_WS_RECONECTADO = "apolo:ws-reconectado";

export type EstadoJob = "corriendo" | "ok" | "error";
const ESTADOS: readonly string[] = ["corriendo", "ok", "error"] satisfies EstadoJob[];

/** `{"type": "job", "job_id", "estado"}` del servidor, ya validado. */
export interface AvisoJob {
  job_id: string;
  estado: EstadoJob;
}

/** El mensaje del WS como objeto JSON, o null si no es JSON o no es un objeto. */
export function mensajeWs(data: unknown): Record<string, unknown> | null {
  if (typeof data !== "string") return null;
  try {
    const m: unknown = JSON.parse(data);
    return typeof m === "object" && m !== null && !Array.isArray(m) ? (m as Record<string, unknown>) : null;
  } catch {
    return null; // mensaje no JSON
  }
}

/** El aviso de job de un mensaje, o null si es de otro tipo, viene roto o trae un estado
   desconocido («encolado» no se manda; si llegara, se ignora). */
export function avisoJob(m: Record<string, unknown> | null): AvisoJob | null {
  if (!m || m.type !== "job") return null;
  const { job_id, estado } = m;
  if (typeof job_id !== "string" || !job_id || typeof estado !== "string" || !ESTADOS.includes(estado)) return null;
  return { job_id, estado: estado as EstadoJob };
}

/** Despacha `EVENTO_JOB` en `destino` si el mensaje es un aviso de job válido. Sin `window`
   (node), no hace nada. */
export function publicarJob(
  m: Record<string, unknown> | null,
  destino: EventTarget | undefined = globalThis.window,
): void {
  const a = avisoJob(m);
  if (a && destino) destino.dispatchEvent(new CustomEvent<AvisoJob>(EVENTO_JOB, { detail: a }));
}

/** Despacha `EVENTO_WS_RECONECTADO` en `destino`. */
export function publicarReconexion(destino: EventTarget | undefined = globalThis.window): void {
  destino?.dispatchEvent(new Event(EVENTO_WS_RECONECTADO));
}
