import type { FaseVivo } from "./estado";

/* Lo que muestra la barra de la sesión viva (plan V8.4, F2 § 5), puro para probarlo: el rótulo
   de la fase, el factor de tiempo real y qué botones van. */

/** Por debajo de esto el factor se pinta en ámbar: la máquina no alcanza al tiempo real (la
 *  medida oscila ±0,4 % alrededor de ×1,00 cuando sí alcanza, Bitácora de F1). */
export const FACTOR_LENTO = 0.995;

export function textoFactor(f: number): { texto: string; lento: boolean } {
  if (!Number.isFinite(f) || f <= 0) return { texto: "×—", lento: false };
  return { texto: `×${f.toFixed(2).replace(".", ",")}`, lento: f < FACTOR_LENTO };
}

export function rotuloFase(fase: FaseVivo): string {
  switch (fase) {
    case "abriendo":
      return "Preparando la simulación…";
    case "corriendo":
      return "En marcha";
    case "pausa":
      return "En pausa";
    case "fin":
      return "Terminó";
    case "error":
      return "Se detuvo";
    default:
      return "Cerrada";
  }
}

/** Qué dice la barra de una pausa que no pidió la persona (`pausa.motivo`), o null (la pausa
 *  manual dice «En pausa» y nada más). `lazo`: se cortó el enlace con el PLC externo y
 *  «Reanudar» lo reintenta (plc-en-el-lazo D8); el `mensaje` del núcleo va al detalle. */
export function avisoPausa(pausa: { motivo: string; mensaje?: string } | null):
  { fase: string; texto: string; detalle?: string } | null {
  if (!pausa) return null;
  if (pausa.motivo === "lazo")
    return {
      fase: "En pausa · se cortó el enlace con el PLC",
      texto: "Revisa que el PLC externo esté encendido y en la red, y reanuda para reintentar.",
      detalle: pausa.mensaje || undefined,
    };
  return { fase: "En pausa", texto: "La simulación se pausó sola.", detalle: pausa.mensaje || undefined };
}

export interface ControlesBarra {
  pausar: boolean;
  reanudar: boolean;
  parar: boolean;
  /** Abrir de nuevo (con `reemplazar=1`): después del fin o de un error. */
  reiniciar: boolean;
}

export function controlesBarra(fase: FaseVivo): ControlesBarra {
  return {
    pausar: fase === "corriendo",
    reanudar: fase === "pausa",
    parar: fase === "corriendo" || fase === "pausa",
    reiniciar: fase === "fin" || fase === "error",
  };
}
