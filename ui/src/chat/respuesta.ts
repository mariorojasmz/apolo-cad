/**
 * La respuesta HTTP de `POST /api/agent/chat` antes de leer su SSE (plan chat-cliente-igual,
 * F9b). Si falló, el error lleva el `detail` de la API, que ya viene escrito para la persona
 * (cupo lleno → 429, configuración inválida → 500); el código queda sólo de respaldo, cuando la
 * respuesta no trae un texto (un proxy caído, la lista de un 422).
 */
import { detalleDeError } from "../api";

/** El cuerpo del stream; si la respuesta falló o vino sin cuerpo, lanza con el motivo. */
export async function cuerpoDelChat(res: Response): Promise<ReadableStream<Uint8Array>> {
  if (res.ok && res.body) return res.body;
  throw new Error((await detalleDeError(res)) ?? `Error ${res.status} del servidor`);
}
