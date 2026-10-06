/* Cambios EXTERNOS (el agente por MCP, el chat autónomo, otro cliente): el refresco por delta
   de la store los publica en `window` y el visor los marca (plan modo-visor, D8). La store no
   conoce al visor: sólo despacha el evento, el mismo patrón desacoplado que `apolo:fit`. Quien
   escucha está en `visor/cambiosExternos.ts`. */
import type { SceneOut } from "../types";
import { cambiosDelDelta, type CambiosDelDelta } from "./sceneDelta";

/** Evento de `window`; su `detail` es un `CambiosDelDelta`. */
export const EVENTO_CAMBIOS_EXTERNOS = "apolo:cambios-externos";

/** Qué publicar de un refresco, o null si no se publica nada. `prev` = la escena ANTES de
   mergear el delta; null si el refresco fue COMPLETO (`refresh(true)`, la reconexión: no marca).
   - El refresco no-completo es externo por construcción: las ediciones propias cierran con su
     propia respuesta y el WS no refresca mientras hay algo nuestro en vuelo.
   - Otro `epoch` = la API reinició y respondió la escena entera: todo vendría «cambiado».
   - Otro proyecto: las piezas no son las mismas aunque compartan id.
   - Sin nada nuevo, cambiado ni eliminado (un cambio de color, por ejemplo), no hay aviso. */
export function cambiosExternos(prev: SceneOut | null, delta: SceneOut): CambiosDelDelta | null {
  if (!prev || delta.epoch !== prev.epoch) return null;
  if (delta.document.project_id !== prev.document.project_id) return null;
  const c = cambiosDelDelta(prev, delta);
  return c.nuevos.length || c.cambiados.length || c.eliminados.length ? c : null;
}

/** Despacha `EVENTO_CAMBIOS_EXTERNOS` en `destino` si hay algo que publicar (ver
   `cambiosExternos`). Sin `window` (node), no hace nada. */
export function publicarCambiosExternos(
  prev: SceneOut | null,
  delta: SceneOut,
  destino: EventTarget | undefined = globalThis.window,
): void {
  const c = cambiosExternos(prev, delta);
  if (c && destino) destino.dispatchEvent(new CustomEvent<CambiosDelDelta>(EVENTO_CAMBIOS_EXTERNOS, { detail: c }));
}
