import type { Accion } from "./mandos";
import type { MandoVivo } from "./protocolo";

/* «Puerta abierta» abre la puerta (plan lo-que-se-mueve, D4): el mando de un resguardo cuya hoja
   cuelga de una junta trae en el `inicio` esa `junta` y sus valores `abierto`/`cerrado` (los
   resuelve el servidor, `services/resguardos.py`). Al accionarlo, la junta va a ese valor como
   cualquier junta del visor (`setJointValue`, que el viewport posa con `applyKinematicPoses`, igual
   que la puerta del tablero en `PanelTablero.tsx`); al cerrar la sesión vuelve al valor que tenía.
   Un resguardo sin junta muestra su estado como siempre: no se inventa movimiento. Puro: el store
   entra como `leer`/`poner` (se prueba en node). */

/** El valor al que lleva la acción la junta del resguardo, o null (sin junta u otra acción). */
export function valorDeJunta(a: Accion, m: MandoVivo): number | null {
  if (m.tipo !== "resguardo" || !m.junta) return null;
  if (a.accion === "abrir" && typeof m.abierto === "number") return m.abierto;
  if (a.accion === "cerrar" && typeof m.cerrado === "number") return m.cerrado;
  return null;
}

export interface JuntasDelVisor {
  leer: (junta: string) => number;
  poner: (junta: string, valor: number) => void;
}

export interface JuntasDeResguardo {
  /** Mueve la junta del resguardo si la acción la abre o la cierra; true si la movió. */
  mover: (a: Accion, m: MandoVivo) => boolean;
  /** Devuelve cada junta que se movió al valor que tenía antes de la primera vez. */
  devolver: () => void;
}

export function crearJuntasDeResguardo(visor: JuntasDelVisor): JuntasDeResguardo {
  const previas = new Map<string, number>();
  return {
    mover(a, m) {
      const v = valorDeJunta(a, m);
      if (v === null || !m.junta) return false;
      if (!previas.has(m.junta)) previas.set(m.junta, visor.leer(m.junta));
      visor.poner(m.junta, v);
      return true;
    },
    devolver() {
      for (const [junta, v] of previas) visor.poner(junta, v);
      previas.clear();
    },
  };
}
