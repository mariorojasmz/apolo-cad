import { useVivo, type FaseVivo } from "../vivo/estado";
import { abrirSesion, enviarMensaje, sesionViva } from "../vivo/sesion";
import type { InicioVivo, PlcExterno } from "../vivo/protocolo";
import type { MensajeExtension } from "./tipos";

/* La API viva DECLARADA para las extensiones de la UI (plan plc-en-el-lazo, D13 c): lo único de la
   sesión viva que una extensión importa (`../vivo`), así no llega a `vivo/` por ruta relativa y el
   núcleo puede mover sus módulos sin romperla. Sólo se AGREGA (como `CONTRATO_EXTENSIONES` del
   lado de Python). Leer: `useFaseVivo` y `useValorVivo` re-pintan un componente (≤ 10 Hz);
   `valorVivo` e `inicioVivo` leen al momento (un canvas, un temporizador). Escribir: `enviarVivo`
   manda una acción o un evento, nunca un control. Abrir: `abrirSesionViva` con un PLC de afuera. */

export type { FaseVivo } from "../vivo/estado";
export type { DispositivoVivo, InicioVivo, PlcExterno } from "../vivo/protocolo";
export type { MensajeExtension, TemaPantalla, VivoPantalla } from "./tipos";

/** La fase de la sesión: `cerrada`, `abriendo`, `corriendo`, `pausa`, `fin` o `error`. */
export function useFaseVivo(): FaseVivo {
  return useVivo((s) => s.fase);
}

/** El valor de una señal (`-M1.rpm`, `-K1.Main.consigna`), re-pintando como mucho a 10 Hz. */
export function useValorVivo(senal: string): number | undefined {
  return useVivo((s) => s.lecturas[senal]);
}

/** El último valor que llegó de una señal, sin re-pintar. */
export function valorVivo(senal: string): number | undefined {
  return sesionViva.valor(senal);
}

/** El `inicio` de la sesión abierta (dispositivos, mandos, señales, `plc_externo`), o null. */
export function inicioVivo(): InicioVivo | null {
  return useVivo.getState().inicio;
}

/** Manda una acción (`{accion: "escribir", dispositivo: "-K1", variable: "Main.consigna", valor:
   50}`) o un evento a la sesión abierta; `false` si no hay sesión o el mensaje no vale. */
export function enviarVivo(mensaje: MensajeExtension): boolean {
  return enviarMensaje(mensaje);
}

/** Abre la sesión viva sobre `escenario`; con `plcExterno` ({"-K1": {conector, config}}), el PLC
   de afuera mueve la máquina (la sesión deja de ser determinista y el servidor lo valida). */
export function abrirSesionViva(escenario: string, opciones: { plcExterno?: PlcExterno } = {}): Promise<void> {
  return abrirSesion(escenario, { plcExterno: opciones.plcExterno });
}
