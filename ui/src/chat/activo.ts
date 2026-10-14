/**
 * ¿Muestra la app el panel del asistente? Lo decide la API: `GET /api/health` → `chat`, que sólo
 * es true si el servidor tiene el chat prendido. Por ahora viene apagado y Apolo se usa desde
 * Claude (D19 del plan chat-cliente-igual). Mientras no se sabe, cuenta como apagado.
 * Es una store para que la barra de paneles del visor se repinte cuando la API responde.
 */
import { create } from "zustand";
import { api } from "../api";

export const useChatActivo = create<{ activo: boolean }>(() => ({ activo: false }));

/** Lo último que dijo la API (false hasta que responde). */
export const chatActivo = (): boolean => useChatActivo.getState().activo;

/** Pregunta a la API si el chat está prendido; un error cuenta como apagado. */
export async function consultarChat(): Promise<boolean> {
  let activo = false;
  try {
    activo = (await api.health()).chat === true;
  } catch {
    activo = false;
  }
  useChatActivo.setState({ activo });
  return activo;
}
