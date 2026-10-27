import * as THREE from "three";
import { materialesDe } from "./zonas";

/* Atenuar las piezas que tapan lo que se encuadró (plan visor-para-evaluar D15): quedan casi
   transparentes, sin escribir profundidad, hasta el próximo encuadre o hasta que el panel que lo
   pidió avise (`EVENTO_RESTAURAR`). Guarda cómo estaba cada material y lo devuelve tal cual; una
   pieza reconstruida en el medio ya trae su material nuevo y no se toca. */

/** Evento de `window` para devolver las piezas atenuadas (lo despacha un panel al cerrarse). */
export const EVENTO_RESTAURAR = "apolo:restaurar-atenuadas";

/** Opacidad de una pieza atenuada: se adivina el contorno, no tapa. */
export const OPACIDAD_ATENUADA = 0.12;

interface Guardado {
  material: THREE.Material;
  transparent: boolean;
  opacity: number;
  depthWrite: boolean;
}

export interface Atenuador {
  atenuar: (mallas: readonly THREE.Object3D[]) => void;
  restaurar: () => void;
  /** Los ids atenuados ahora (para los tests y el hook de depuración). */
  ids: () => string[];
}

export function crearAtenuador(): Atenuador {
  let guardados: Guardado[] = [];
  let ids: string[] = [];
  const restaurar = () => {
    for (const g of guardados) {
      g.material.transparent = g.transparent;
      g.material.opacity = g.opacity;
      g.material.depthWrite = g.depthWrite;
      g.material.needsUpdate = true;
    }
    guardados = [];
    ids = [];
  };
  return {
    atenuar: (mallas) => {
      restaurar();
      const vistos = new Set<THREE.Material>();
      for (const m of mallas) {
        ids.push(String(m.userData.featureId));
        m.traverse((o) => {
          const mats = materialesDe((o as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined);
          for (const mat of mats) {
            if (!mat || vistos.has(mat)) continue;
            vistos.add(mat);
            guardados.push({ material: mat, transparent: mat.transparent, opacity: mat.opacity, depthWrite: mat.depthWrite });
            mat.transparent = true;
            mat.opacity = Math.min(mat.opacity, OPACIDAD_ATENUADA);
            mat.depthWrite = false;
            mat.needsUpdate = true;
          }
        });
      }
    },
    restaurar,
    ids: () => [...ids],
  };
}
