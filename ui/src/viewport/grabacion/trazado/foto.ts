import type * as THREE from "three";
import type { Pipeline } from "../../pipeline";
import { crearCaptura } from "../captura";
import { nombreGpu, sinGpu } from "../enVista";
import { entrarModoGrabacion } from "../modo";
import { opcionesTrazado, tamanoFoto, TRAZADO_FOTO, type OpcionesTrazado } from "./nivel";
import type { ControlTrazado, InformeTrazado } from "./trazador";

/* «Foto realista» del visor (plan video-realista, D6): lo que se ve en el visor —la misma escena,
   cámara, materiales (tabla de acabados y zonas) y el estudio del visor «alta»—, trazado con el
   nivel MÁXIMO y entregado como PNG. El encuadre es el de la vista (su proporción, con el lado
   mayor en 1920 px por defecto); la pose, la de ese instante (con la marcha, la que se ve). */

export interface OpcionesFoto extends ControlTrazado {
  /** Lado mayor de la foto (px). */
  lado?: number;
  trazado?: Partial<OpcionesTrazado>;
  permitirSinGpu?: boolean;
}

export interface Foto extends InformeTrazado {
  png: Blob;
  gpu: string | null;
  segundos: number;
}

export type FotoRealista = (op?: OpcionesFoto) => Promise<Foto>;

let actual: FotoRealista | null = null;

/** La registra el visor al montarse (como el grabador, `registro.ts`); devuelve la limpieza. */
export function registrarFoto(f: FotoRealista): () => void {
  actual = f;
  return () => {
    if (actual === f) actual = null;
  };
}

export const fotoRegistrada = (): FotoRealista | null => actual;

let ocupada = false;

/** Hay una foto trazándose (el visor está en modo grabación: no se puede grabar a la vez). */
export const fotoEnCurso = () => ocupada;

export function crearFotoRealista(pipe: Pipeline, ocultar: () => THREE.Object3D[]): FotoRealista {
  return async (op = {}) => {
    if (ocupada) throw new Error("Ya estamos sacando una foto: espera a que termine.");
    const gpu = nombreGpu(pipe.renderer);
    if (sinGpu(gpu) && !op.permitirSinGpu) {
      throw new Error("Este navegador dibuja sin GPU y la foto tardaría horas. Abre Apolo en un "
        + "navegador con aceleración por hardware.");
    }
    ocupada = true;
    const t0 = performance.now();
    const lienzo = pipe.renderer.domElement;
    const { ancho, alto } = tamanoFoto(lienzo.clientWidth, lienzo.clientHeight, op.lado);
    const trazado = opcionesTrazado(TRAZADO_FOTO, op.trazado);
    const modo = entrarModoGrabacion(pipe, { ancho, alto, nivel: "maximo", trazado, ocultar: ocultar() });
    try {
      const inf = await modo.cuadro(performance.now(), { progreso: op.progreso, cancelado: op.cancelado });
      const { foto } = crearCaptura(ancho, alto, "png").tomar(lienzo); // en el mismo hilo
      const png = await foto;
      return { ...inf!, png, gpu, segundos: (performance.now() - t0) / 1000 };
    } finally {
      modo.salir();
      ocupada = false;
    }
  };
}
