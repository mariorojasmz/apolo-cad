import type { EstadoVivo } from "./estado";
import type { Accion, EstadoMando } from "./mandos";
import type { MandoVivo } from "./protocolo";

/* El estado de un mando para el panel y para su pieza 3D: lo que dicen las señales, con lo
   recién pedido encima hasta que la señal lo muestre. Puro (el envío es `sesion.accionar`). */

/** La señal que muestra el estado de un mando de una sola posición, o null. */
export function senalDeEstado(m: MandoVivo): string | null {
  if (m.tipo === "seccionador") return `${m.designacion}.cerrado`;
  if ((m.tipo === "seta" || m.tipo === "pulsador") && m.senales.includes(`${m.designacion}.accionado`)) {
    return `${m.designacion}.accionado`;
  }
  return null;
}

/** El valor de una señal con lo recién pedido encima (hasta que la señal lo muestre). */
export function valorVisto(st: Pick<EstadoVivo, "lecturas" | "esperadas">, senal: string): number | undefined {
  return st.esperadas[senal] ?? st.lecturas[senal];
}

export function estadoDeMando(m: MandoVivo, st: Pick<EstadoVivo, "lecturas" | "esperadas">): EstadoMando {
  const senal = senalDeEstado(m);
  return estadoDesdeValor(m, senal ? valorVisto(st, senal) : undefined);
}

/** El estado de un mando desde el valor de su señal de estado (`senalDeEstado`). */
export function estadoDesdeValor(m: MandoVivo, v: number | undefined): EstadoMando {
  if (m.tipo === "seta") return { retenida: v !== undefined && v >= 0.5 };
  if (m.tipo === "seccionador") return { cerrado: v === undefined ? undefined : v >= 0.5 };
  return {};
}

/** Lo que la acción va a dejar en la señal de estado del mando, si se sabe. */
export function esperaDe(a: Accion, m: MandoVivo): { senal: string; valor: number } | undefined {
  const senal = senalDeEstado(m);
  if (!senal || a.actuador !== undefined) return undefined;
  // los nombres de las acciones son los del protocolo (`cosim/escenario.py`)
  const valor = ({ pulsar: 1, soltar: 0, presionar: 1, liberar: 0, cerrar: 1, abrir: 0 } as Record<string, number>)[String(a.accion)]; // voseo-interno
  if (valor === undefined) return undefined;
  if (m.tipo === "pulsador" && m.retorno === "mantenido") return undefined; // alterna: no se sabe
  return { senal, valor };
}
