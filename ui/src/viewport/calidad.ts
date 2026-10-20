import { create } from "zustand";

/* Interruptor de CALIDAD del visor (video-realista D1): «alta» = estudio procedural como luz de
   ambiente + oclusión ambiental (GTAO) + antialias SMAA; «normal» = el visor de antes
   (RoomEnvironment y MSAA ×4), para PCs flojas. Store propia (la general está en su tope).

   Por defecto, «alta», salvo que la GPU sea integrada o por software (F0: en una Intel UHD
   «alta» cuesta ~30 % de los fps). Lo que la persona elige se recuerda en este navegador
   (`localStorage`, con try/catch: en una ventana privada puede fallar y no pasa nada). */

export type Calidad = "alta" | "normal";

export const CLAVE_LOCAL = "apolo.visor.calidad";

/** GPU integrada o por software, por el nombre que da `WEBGL_debug_renderer_info`. */
const GPU_FLOJA = /swiftshader|llvmpipe|software|basic render|mali|adreno|powervr|videocore/i;
/** Intel integrada (UHD, Iris, HD Graphics); una Intel Arc es dedicada y no cuenta. */
const INTEL_INTEGRADA = /intel(?!.*\barc\b)/i;

export function gpuFloja(nombre: string | null | undefined): boolean {
  return !!nombre && (GPU_FLOJA.test(nombre) || INTEL_INTEGRADA.test(nombre));
}

function leerGuardada(): Calidad | null {
  try {
    const v = globalThis.localStorage?.getItem(CLAVE_LOCAL);
    return v === "alta" || v === "normal" ? v : null;
  } catch {
    return null;
  }
}

function guardar(c: Calidad): void {
  try {
    globalThis.localStorage?.setItem(CLAVE_LOCAL, c);
  } catch {
    /* sin almacenamiento: la elección dura lo que dure la página */
  }
}

interface EstadoCalidad {
  calidad: Calidad;
  /** La persona eligió (se recuerda). */
  fijar: (c: Calidad) => void;
  /** El visor conoce su GPU: si nadie eligió, una GPU floja arranca en «normal». */
  sugerirPorGpu: (nombre: string | null | undefined) => void;
}

export const useCalidad = create<EstadoCalidad>((set) => ({
  calidad: leerGuardada() ?? "alta",
  fijar: (calidad) => {
    guardar(calidad);
    set({ calidad });
  },
  sugerirPorGpu: (nombre) => {
    if (leerGuardada() === null && gpuFloja(nombre)) set({ calidad: "normal" });
  },
}));
