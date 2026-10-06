/**
 * El protocolo del chat: el SSE de `POST /api/agent/chat` → eventos tipados (plan
 * chat-cliente-igual, F9). PURO: sin React ni store; lo consume `state/store.ts::sendChat`.
 *
 * Un evento nuevo del backend (`core/apolo/agent/modelo.py` y el ejecutor del chat) se agrega
 * AQUÍ: su forma en `EventoChat`, su validación en `validar()` y su caso en `sse.test.ts`.
 *
 * Lectura (subconjunto del estándar SSE que usa la API): líneas terminadas en `\n`, `\r\n` o
 * `\r`; los `data:` se juntan con `\n` y una línea vacía despacha el evento; `:` es un
 * comentario y los otros campos (`event`, `id`, `retry`) se ignoran. Los trozos pueden cortar
 * una línea, un `\r\n` o un carácter UTF-8 por la mitad (esto último lo absorbe `TextDecoder`).
 *
 * **Lo que no se entiende no tumba el stream**:
 * - un `type` desconocido se ignora en silencio (compatibilidad hacia adelante);
 * - JSON roto, algo que no es un objeto con `type`, o un tipo conocido sin sus campos se
 *   DESCARTA y se avisa a `alDescartar` (el store lo manda a `logs/errors.log`): es un bug del
 *   backend, no algo que la persona pueda arreglar, así que no se pinta en el chat;
 * - un evento a medias al cerrar el stream no se despacha (como manda el estándar) y también
 *   se avisa.
 */
import type { ChatAction, UsoTurno } from "../types";

export type EventoChat =
  | { type: "text"; text: string }
  /** Nota de avance del modelo entre tools: línea transitoria. Una nota puede llegar en varios
   *  trozos; `nuevo` marca el primero (sólo viene en true; un backend sin la marca no lo manda). */
  | { type: "progreso"; text: string; nuevo?: boolean }
  /** `etiqueta` = texto para la persona («Leyendo el modelo»); el chat viejo no la manda. */
  | { type: "tool"; name: string; etiqueta?: string }
  | { type: "actions"; actions: ChatAction[]; executed: boolean }
  /** El turno terminó incompleto (no falló). `motivo`: max_tokens, refusal,
   *  model_context_window_exceeded, vueltas, otro. `mensaje` ya viene en tuteo. */
  | { type: "aviso"; motivo: string; mensaje: string }
  | { type: "error"; message: string }
  /** Cierra el turno; `uso` = tokens de todas las llamadas al modelo del turno. */
  | { type: "done"; uso?: UsoTurno };

export type AlDescartar = (detalle: string) => void;

const TOPE_CRUDO = 200;
const recorte = (s: string) => (s.length > TOPE_CRUDO ? `${s.slice(0, TOPE_CRUDO)}…` : s);
const esTexto = (v: unknown): v is string => typeof v === "string";
const esNumero = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function uso(v: unknown): UsoTurno | undefined {
  if (typeof v !== "object" || v === null) return undefined;
  const u = v as Record<string, unknown>;
  const n = (k: string) => (esNumero(u[k]) ? (u[k] as number) : 0);
  return { input: n("input"), output: n("output"), cache_read: n("cache_read"), cache_creation: n("cache_creation") };
}

/** El evento tipado, `null` si es de un tipo desconocido o `string` (el motivo) si no sirve. */
export function validar(dato: unknown): EventoChat | null | string {
  if (typeof dato !== "object" || dato === null || Array.isArray(dato)) return "no es un objeto";
  const d = dato as Record<string, unknown>;
  if (!esTexto(d.type)) return "sin `type`";
  const falta = (campo: string) => `\`${d.type}\` sin \`${campo}\``;
  switch (d.type) {
    case "text":
      return esTexto(d.text) ? { type: "text", text: d.text } : falta("text");
    case "progreso":
      if (!esTexto(d.text)) return falta("text");
      return d.nuevo === true ? { type: "progreso", text: d.text, nuevo: true } : { type: "progreso", text: d.text };
    case "tool":
      if (!esTexto(d.name)) return falta("name");
      return esTexto(d.etiqueta) && d.etiqueta.trim()
        ? { type: "tool", name: d.name, etiqueta: d.etiqueta }
        : { type: "tool", name: d.name };
    case "actions":
      return Array.isArray(d.actions)
        ? { type: "actions", actions: d.actions as ChatAction[], executed: d.executed === true }
        : falta("actions");
    case "aviso":
      return esTexto(d.mensaje)
        ? { type: "aviso", motivo: esTexto(d.motivo) ? d.motivo : "otro", mensaje: d.mensaje }
        : falta("mensaje");
    case "error":
      return esTexto(d.message) ? { type: "error", message: d.message } : falta("message");
    case "done": {
      const u = uso(d.uso);
      return u ? { type: "done", uso: u } : { type: "done" };
    }
    default:
      return null;
  }
}

/** Parser incremental: `push(trozo)` devuelve los eventos que el trozo completó. */
export function crearLectorSse(alDescartar: AlDescartar = () => undefined) {
  let buffer = "";
  let datos: string[] = [];

  const despachar = (salida: EventoChat[]) => {
    if (datos.length === 0) return;
    const crudo = datos.join("\n");
    datos = [];
    let dato: unknown;
    try {
      dato = JSON.parse(crudo);
    } catch {
      alDescartar(`JSON inválido: ${recorte(crudo)}`);
      return;
    }
    const ev = validar(dato);
    if (typeof ev === "string") alDescartar(`${ev}: ${recorte(crudo)}`);
    else if (ev) salida.push(ev);
  };

  const linea = (l: string, salida: EventoChat[]) => {
    if (l === "") return despachar(salida);
    if (l.startsWith(":")) return; // comentario (latido)
    const dos = l.indexOf(":");
    const campo = dos < 0 ? l : l.slice(0, dos);
    if (campo !== "data") return;
    const valor = dos < 0 ? "" : l.slice(dos + 1);
    datos.push(valor.startsWith(" ") ? valor.slice(1) : valor);
  };

  return {
    push(trozo: string): EventoChat[] {
      buffer += trozo;
      const salida: EventoChat[] = [];
      for (;;) {
        const fin = /\r\n|\n|\r/.exec(buffer);
        if (!fin) break;
        // un `\r` al final puede ser la mitad de un `\r\n`: se espera al próximo trozo
        if (fin[0] === "\r" && fin.index === buffer.length - 1) break;
        const l = buffer.slice(0, fin.index);
        buffer = buffer.slice(fin.index + fin[0].length);
        linea(l, salida);
      }
      return salida;
    },
    /** Cierre del stream: un `\r` final cierra su línea; lo que quedó sin línea vacía no se despacha. */
    fin(): EventoChat[] {
      const salida: EventoChat[] = [];
      const resto = buffer;
      buffer = "";
      if (resto.endsWith("\r")) linea(resto.slice(0, -1), salida);
      else if (resto) linea(resto, salida);
      if (datos.length) alDescartar(`evento incompleto al cerrar: ${recorte(datos.join("\n"))}`);
      datos = [];
      return salida;
    },
  };
}

/** Los eventos de un cuerpo de `fetch`, en orden. Si quien consume corta antes, cancela el stream. */
export async function* eventosSse(
  cuerpo: ReadableStream<Uint8Array>,
  alDescartar?: AlDescartar,
): AsyncGenerator<EventoChat> {
  const lector = crearLectorSse(alDescartar);
  const decoder = new TextDecoder();
  const reader = cuerpo.getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      yield* lector.push(decoder.decode(value, { stream: true }));
    }
    yield* lector.push(decoder.decode());
    yield* lector.fin();
  } finally {
    reader.cancel().catch(() => undefined);
  }
}
