import { create } from "zustand";
import type { EventoFalla } from "./fallas";
import type { InicioVivo, ProblemaVivo } from "./protocolo";

/* Estado de la sesión viva para la interfaz (plan V8.4): el panel «Mandos» y la barra de la
   sesión lo leen; lo escribe `sesion.ts`, que recibe el WebSocket. Las lecturas (señales) se
   publican como mucho a 10 Hz: el 3D no pasa por aquí, lee el último fotograma directo. */

export type FaseVivo = "cerrada" | "abriendo" | "corriendo" | "pausa" | "fin" | "error";

export interface EstadoVivo {
  fase: FaseVivo;
  escenario: string | null;
  inicio: InicioVivo | null;
  /** Tiempo virtual de la última muestra (s). */
  t: number;
  /** Factor de tiempo real medido (1 = tiempo real). */
  factor: number;
  /** La firma del documento cambió: la sesión simula el modelo de cuando se abrió (D3). */
  vieja: boolean;
  /** Valores de las señales por nombre (el último que llegó de cada una). */
  lecturas: Record<string, number>;
  /** Señales de texto (estado del variador, del PLC, su falla). */
  textos: Record<string, string>;
  /** Lo que se acaba de pedir y su señal todavía no muestra (la seta presionada, el seccionador
   *  abierto): el panel lo muestra así hasta que la señal coincida o la acción se rechace. */
  esperadas: Record<string, number>;
  /** Las fallas de rama puestas (las de un aparato llegan en `<des>.averia`, en `textos`; las
   *  de la red no publican señal y se llevan por el ack de su evento, `fallas.ts`). */
  ramasEnFalla: readonly EventoFalla[];
  /** El último rechazo de una acción, ya en palabras. */
  rechazo: string | null;
  problema: ProblemaVivo | null;
  /** Por qué está en pausa, si no la pidió la persona: `lazo` (se cortó el enlace con el PLC
   *  externo, plc-en-el-lazo D8) con el `mensaje` del núcleo. null en una pausa manual. */
  pausa: { motivo: string; mensaje?: string } | null;
  /** Por qué terminó (texto) y en qué instante. */
  fin: { texto: string; t: number } | null;
  set: (p: Partial<EstadoVivo>) => void;
}

export const INICIAL = {
  fase: "cerrada" as FaseVivo,
  escenario: null,
  inicio: null,
  t: 0,
  factor: 1,
  vieja: false,
  lecturas: {},
  textos: {},
  esperadas: {},
  ramasEnFalla: [] as readonly EventoFalla[],
  rechazo: null,
  problema: null,
  pausa: null,
  fin: null,
} satisfies Omit<EstadoVivo, "set">;

export const useVivo = create<EstadoVivo>((set) => ({
  ...INICIAL,
  set: (p) => set(p),
}));
