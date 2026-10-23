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
