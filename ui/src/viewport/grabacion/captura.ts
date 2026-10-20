import { BACKGROUND_CSS } from "../scene-setup";
import type { CuadroDibujado } from "./reloj";
import type { FormatoCuadro } from "./grabador";

/* Foto de cada cuadro (plan video-realista, D3/D4). El canvas del visor es TRANSPARENTE (el fondo
   lo pinta el CSS del contenedor, `scene-setup.ts`), así que la foto se arma en un lienzo 2D: el
   color de fondo del visor y encima el cuadro. `drawImage` copia el canvas de WebGL en el MISMO
   hilo en que se dibujó (sin `preserveDrawingBuffer` se borra al soltarlo) y `toBlob` codifica
   después, fuera del hilo, mientras se dibuja el siguiente cuadro.

   Con el guion (F3, D5) el lienzo 2D también pone lo que el video de VTK hace con numpy y Pillow,
   con los valores del plan: el rótulo de la etapa (una capa de la API) con su fundido, el fundido
   cruzado desde el último cuadro de la parte anterior y el fundido desde y hacia negro.

   JPEG 0,95 por defecto (medido en F2 con una captura real a 1080p: 42 ms y ~350 KB por cuadro,
   contra 113 ms y 1,7 MB del PNG; tras el H.264 a CRF 18 pierde ~2,7 dB de PSNR, invisible).
   PNG queda para cuando se quiera la foto sin pérdida. */

export const CALIDAD_JPEG = 0.95;
/** Lienzos en rotación: `toBlob` toma su copia al llamarlo, dos sobran para no pisarse. */
const LIENZOS = 2;

export interface Efectos {
  /** El rótulo (capa transparente del tamaño del cuadro) y su opacidad (0–1). */
  rotulo?: { imagen: CanvasImageSource; opacidad: number } | null;
  /** Primer cuadro de una parte que entra con fundido: lo anterior queda como origen. */
  empiezaCruce?: boolean;
  /** Fundido cruzado: 0 = el cuadro anterior, 1 = el nuevo; null/undefined = sin fundido. */
  mezcla?: number | null;
  /** 1 = normal; menos, hacia negro (fundido del principio y del final). */
  luz?: number;
}

export interface Captura {
  /** Copia `origen` (el canvas recién dibujado o una tarjeta) con sus efectos y devuelve la
     foto que se está codificando. */
  tomar: (origen: CanvasImageSource, efectos?: Efectos) => CuadroDibujado;
}

function lienzo(ancho: number, alto: number): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = ancho;
  c.height = alto;
  return c;
}

export function crearCaptura(ancho: number, alto: number, formato: FormatoCuadro): Captura {
  const lienzos = Array.from({ length: LIENZOS }, () => lienzo(ancho, alto));
  let ultimo: HTMLCanvasElement | null = null; // el cuadro anterior, sin el fundido a negro
  let desde: HTMLCanvasElement | null = null; // de dónde sale el fundido cruzado en curso
  let hayUltimo = false;
  let hayDesde = false;
  const tipo = formato === "png" ? "image/png" : "image/jpeg";
  let i = 0;
  return {
    tomar: (origen, ef = {}) => {
      const usaEfectos = ef.mezcla != null || ef.empiezaCruce || (ef.luz ?? 1) < 1 || !!ef.rotulo;
      if (usaEfectos && !ultimo) {
        ultimo = lienzo(ancho, alto);
        desde = lienzo(ancho, alto);
      }
      if (ef.empiezaCruce && desde && ultimo) {
        desde.getContext("2d")!.drawImage(ultimo, 0, 0);
        hayDesde = hayUltimo;
      }
      const destino = lienzos[i++ % LIENZOS];
      const ctx = destino.getContext("2d")!;
      ctx.globalAlpha = 1;
      ctx.fillStyle = BACKGROUND_CSS;
      ctx.fillRect(0, 0, ancho, alto);
      ctx.drawImage(origen, 0, 0, ancho, alto);
      if (ef.rotulo && ef.rotulo.opacidad > 0) {
        ctx.globalAlpha = Math.min(ef.rotulo.opacidad, 1);
        ctx.drawImage(ef.rotulo.imagen, 0, 0, ancho, alto);
        ctx.globalAlpha = 1;
      }
      if (ef.mezcla != null && desde && hayDesde) {
        // anterior·(1−m) + nuevo·m: lo anterior encima con alfa 1−m
        ctx.globalAlpha = 1 - Math.min(Math.max(ef.mezcla, 0), 1);
        ctx.drawImage(desde, 0, 0);
        ctx.globalAlpha = 1;
      }
      if (ultimo) {
        ultimo.getContext("2d")!.drawImage(destino, 0, 0);
        hayUltimo = true;
      }
      const luz = Math.min(Math.max(ef.luz ?? 1, 0), 1);
      if (luz < 1) {
        ctx.fillStyle = `rgba(0, 0, 0, ${1 - luz})`;
        ctx.fillRect(0, 0, ancho, alto);
      }
      const foto = new Promise<Blob>((res, rej) =>
        destino.toBlob((b) => (b ? res(b) : rej(new Error("El navegador no pudo codificar el cuadro."))),
          tipo, formato === "png" ? undefined : CALIDAD_JPEG));
      return { foto };
    },
  };
}
