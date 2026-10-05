/**
 * Cómo cambia el mensaje del asistente con cada evento del chat (plan chat-cliente-igual, F9).
 * PURO: el store aplica el resultado y hace los efectos (refrescar la escena tras un lote
 * ejecutado). Los eventos llegan ya tipados de `sse.ts`.
 *
 * **La nota de avance** (`progreso`) es UNA línea transitoria: una nota nueva reemplaza a la
 * anterior y la borran el texto, `done`, un error o el cierre del stream. Los `progreso`
 * SEGUIDOS se juntan en la misma nota: el backend reenvía cada `thinking_delta` y la API puede
 * partir la nota de un bloque en varios deltas; una tool, un lote o un aviso en medio la
 * cierran, y el próximo `progreso` empieza una nota nueva.
 */
import type { ChatMsg } from "../types";
import type { EventoChat } from "./sse";

/** El stream terminó sin `done` ni error: la respuesta quedó a medias. */
export const CORTADO = "La conexión se cortó antes de que terminara la respuesta: vuelve a intentarlo.";

/** `seguido`: el evento anterior del turno también fue `progreso`. */
export function aplicarEvento(msg: ChatMsg, ev: EventoChat, seguido: boolean): ChatMsg {
  switch (ev.type) {
    case "text":
      return { ...msg, content: msg.content + ev.text, progreso: undefined };
    case "progreso":
      return { ...msg, progreso: (seguido ? msg.progreso ?? "" : "") + ev.text };
    case "tool": {
      const tool = ev.etiqueta ? { name: ev.name, etiqueta: ev.etiqueta } : { name: ev.name };
      return { ...msg, tools: [...(msg.tools ?? []), tool] };
    }
    case "actions":
      // autónomo: el lote ya corrió y se acumula; propuesta: espera Aceptar/Rechazar
      return ev.executed
        ? { ...msg, actions: [...(msg.actions ?? []), ...ev.actions], actionsStatus: "accepted" }
        : { ...msg, actions: ev.actions, actionsStatus: "pending" };
    case "aviso":
      return { ...msg, aviso: msg.aviso ? `${msg.aviso}\n${ev.mensaje}` : ev.mensaje };
    case "error":
      return { ...msg, error: ev.message, progreso: undefined };
    case "done":
      return { ...msg, progreso: undefined, ...(ev.uso ? { uso: ev.uso } : {}) };
  }
}

/** Cierre del stream: sin nota de avance y, si nunca llegó `done` ni un error, lo dice. */
export function cerrarTurno(msg: ChatMsg, terminado: boolean): ChatMsg {
  const cerrado = { ...msg, progreso: undefined };
  return terminado || msg.error ? cerrado : { ...cerrado, error: CORTADO };
}
