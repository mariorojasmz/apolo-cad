import { cifra } from "../diseno/cifra";
import type { Historia } from "../vivo/historia";

/* El aire que consume la máquina en la sesión viva (plan V8.9 D12): la barra suma
   «Aire: 14 NL/min», la MEDIA MÓVIL del caudal de cada FRL (`<des>.Q_Nl_min`, D7) en los últimos
   `VENTANA_S` segundos de la historia de la sesión (`vivo/historia.ts`). El caudal instantáneo
   salta de 0 a cientos de NL/min en cada carrera: la media es lo que se compara con el compresor.
   Puro. */

/** Ventana de la media móvil (s): varios ciclos de una máquina de manejo de materiales (criterio). */
export const VENTANA_S = 10;

/** Las señales de caudal de los FRL que llegaron en la sesión. */
export function senalesDeAire(nombres: Iterable<string>): string[] {
  return [...new Set([...nombres].filter((n) => n.endsWith(".Q_Nl_min")))].sort();
}

/** La media de la suma de los caudales en la ventana que termina en la última muestra, o
   undefined sin muestras. Cada señal promedia sus muestras con valor (las NaN se saltan). */
export function aireMedio(h: Historia, senales: readonly string[], ventana = VENTANA_S): number | undefined {
  const tU = h.tUltimo();
  if (tU === null || !senales.length) return undefined;
  const desde = h.desde(tU - ventana);
  let total = 0;
  let alguna = false;
  for (const s of senales) {
    let suma = 0;
    let n = 0;
    for (let k = desde; k < h.n; k++) {
      const v = h.valor(s, k);
      if (Number.isFinite(v)) {
        suma += v;
        n++;
      }
    }
    if (n) {
      total += suma / n;
      alguna = true;
    }
  }
  return alguna ? total : undefined;
}

/** «14 NL/min» (sin decimales sobre 10; uno debajo). */
export function textoAire(nl: number): string {
  return cifra(nl, nl >= 10 ? 0 : 1, "NL/min");
}
