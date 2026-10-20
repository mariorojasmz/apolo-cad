import { cuadrosPara } from "./reloj";

/* Lo que se graba en F2 (plan video-realista): la máquina GIRANDO y, si hay una marcha cargada,
   ANDANDO con su serie (visor-realista F2/F3). La cámara parte del encuadre que tiene el visor y
   da `grados` alrededor del eje Z por el centro de la vista, con arranque y frenado suaves (la
   misma curva que la órbita del video de la tienda, `publicacion/linea_tiempo.py`). El guion
   completo del video (montaje, rótulos y giro final, D5) es de F3. Puro: sin three ni DOM. */

/** Sin marcha, cuánto dura el giro (s); con marcha, el video dura lo que ella, hasta este tope. */
export const SEGUNDOS_GIRO = 8;
export const SEGUNDOS_MAX = 60;
export const GRADOS_GIRO = 360;

type Punto = [number, number, number];

export interface PlanGiro {
  fps: number;
  cuadros: number;
  segundos: number;
  /** Duración de la marcha (s) o null si no hay. */
  marcha: number | null;
  grados: number;
}

export function planGiro(op: {
  fps: number; marchaSegundos?: number | null; segundos?: number; grados?: number;
}): PlanGiro {
  const marcha = op.marchaSegundos && op.marchaSegundos > 0 ? op.marchaSegundos : null;
  const segundos = Math.min(op.segundos ?? marcha ?? SEGUNDOS_GIRO, SEGUNDOS_MAX);
  return { fps: op.fps, cuadros: cuadrosPara(segundos, op.fps), segundos, marcha,
    grados: op.grados ?? GRADOS_GIRO };
}

/** Fracción de la órbita en el cuadro `n`: 0 en el primero, 1 en el último, suavizada. */
export function avanceGiro(n: number, cuadros: number): number {
  const x = cuadros > 1 ? Math.min(Math.max(n / (cuadros - 1), 0), 1) : 0;
  return x * x * (3 - 2 * x);
}

/** Tiempo de la marcha en el cuadro `n` (s): el del video, sin pasarse del final de la serie. */
export function tiempoMarcha(plan: PlanGiro, n: number): number {
  return plan.marcha === null ? 0 : Math.min(n / plan.fps, plan.marcha);
}

/** Posición de la cámara en el cuadro `n`: `desde` girado alrededor del eje Z que pasa por
   `objetivo` (Z arriba en Apolo); la altura y la distancia no cambian. */
export function posicionGiro(objetivo: Punto, desde: Punto, plan: PlanGiro, n: number): Punto {
  const a = (plan.grados * avanceGiro(n, plan.cuadros) * Math.PI) / 180;
  const dx = desde[0] - objetivo[0];
  const dy = desde[1] - objetivo[1];
  const c = Math.cos(a);
  const s = Math.sin(a);
  return [objetivo[0] + dx * c - dy * s, objetivo[1] + dx * s + dy * c, desde[2]];
}
