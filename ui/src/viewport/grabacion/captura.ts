import { BACKGROUND_CSS } from "../scene-setup";
import type { CuadroDibujado } from "./reloj";
import type { FormatoCuadro } from "./grabador";

/* Foto de cada cuadro (plan video-realista, D3/D4). El canvas del visor es TRANSPARENTE (el fondo
   lo pinta el CSS del contenedor, `scene-setup.ts`), así que la foto se arma en un lienzo 2D: el
   color de fondo del visor y encima el cuadro. `drawImage` copia el canvas de WebGL en el MISMO
   hilo en que se dibujó (sin `preserveDrawingBuffer` se borra al soltarlo) y `toBlob` codifica
   después, fuera del hilo, mientras se dibuja el siguiente cuadro.

   JPEG 0,95 por defecto (medido en F2 con una captura real a 1080p: 42 ms y ~350 KB por cuadro,
   contra 113 ms y 1,7 MB del PNG; tras el H.264 a CRF 18 pierde ~2,7 dB de PSNR, invisible).
   PNG queda para cuando se quiera la foto sin pérdida. */

export const CALIDAD_JPEG = 0.95;
/** Lienzos en rotación: `toBlob` toma su copia al llamarlo, dos sobran para no pisarse. */
const LIENZOS = 2;

export interface Captura {
  /** Copia `origen` (el canvas recién dibujado) y devuelve la foto que se está codificando. */
  tomar: (origen: CanvasImageSource) => CuadroDibujado;
}

export function crearCaptura(ancho: number, alto: number, formato: FormatoCuadro): Captura {
  const lienzos = Array.from({ length: LIENZOS }, () => {
    const c = document.createElement("canvas");
    c.width = ancho;
    c.height = alto;
    return c;
  });
  const tipo = formato === "png" ? "image/png" : "image/jpeg";
  let i = 0;
  return {
    tomar: (origen) => {
      const lienzo = lienzos[i++ % LIENZOS];
      const ctx = lienzo.getContext("2d")!;
      ctx.fillStyle = BACKGROUND_CSS;
      ctx.fillRect(0, 0, ancho, alto);
      ctx.drawImage(origen, 0, 0, ancho, alto);
      const foto = new Promise<Blob>((res, rej) =>
        lienzo.toBlob((b) => (b ? res(b) : rej(new Error("El navegador no pudo codificar el cuadro."))),
          tipo, formato === "png" ? undefined : CALIDAD_JPEG));
      return { foto };
    },
  };
}
