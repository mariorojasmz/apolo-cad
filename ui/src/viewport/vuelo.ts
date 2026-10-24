import * as THREE from "three";
import { MOV_NORMAL_MS, movimientoReducido, suave } from "../diseno/movimiento";
import type { PoseCamara } from "./camara";

/* Vuelo de cámara (plan V8.5 D13–D14, F3b-0): el encuadre que pide `apolo:fit` con
   `animar: true` se recorre en ≈ 320 ms con la curva `--curva-suave`, en vez de saltar. Con
   `prefers-reduced-motion`, salta. El vuelo es una tarea del bucle (`pipeline.antesDeComponer`)
   y usa el `ahora` que recibe, nunca el reloj real (al grabar, el reloj es virtual). Si la
   persona agarra la cámara (órbita, pan, rueda), el vuelo se corta ahí. */

/** Lo que el vuelo necesita de los controles (OrbitControls cumple). */
export interface ControlesVuelo {
  target: THREE.Vector3;
  update: () => unknown;
  addEventListener?: (tipo: "start", fn: () => void) => void;
  removeEventListener?: (tipo: "start", fn: () => void) => void;
}

export interface VueloCamara {
  /** Vuela hasta `destino` (o salta, con movimiento reducido o `duracionMs` 0). */
  volar: (destino: PoseCamara, duracionMs?: number) => void;
  /** La tarea del bucle: mueve la cámara al punto del vuelo en `ahora` (ms). */
  tick: (ahora: number) => void;
  /** Deja la cámara donde está. */
  cancelar: () => void;
  enCurso: () => boolean;
  /** Suelta el aviso de los controles. */
  dispose: () => void;
}

/** La pose a la fracción `k` (0 → `desde`, 1 → `hasta`; ya con la curva aplicada). El objetivo
   va en línea recta; la vista gira por el arco corto y la distancia cambia en proporción (un
   acercamiento grande no se precipita al final). Puro. */
export function poseEn(desde: PoseCamara, hasta: PoseCamara, k: number): PoseCamara {
  const objetivo = desde.objetivo.clone().lerp(hasta.objetivo, k);
  const o0 = desde.posicion.clone().sub(desde.objetivo);
  const o1 = hasta.posicion.clone().sub(hasta.objetivo);
  const d0 = o0.length(), d1 = o1.length();
  if (!(d0 > 1e-9) || !(d1 > 1e-9)) {
    return { posicion: desde.posicion.clone().lerp(hasta.posicion, k), objetivo };
  }
  const giro = new THREE.Quaternion().setFromUnitVectors(o0.clone().divideScalar(d0), o1.clone().divideScalar(d1));
  const dir = o0.divideScalar(d0).applyQuaternion(new THREE.Quaternion().slerp(giro, k));
  const d = d0 * Math.pow(d1 / d0, k);
  return { posicion: objetivo.clone().addScaledVector(dir, d), objetivo };
}

export function crearVueloCamara(
  camera: THREE.Camera, controls: ControlesVuelo, reducido: () => boolean = movimientoReducido,
): VueloCamara {
  let vuelo: { desde: PoseCamara; hasta: PoseCamara; dur: number; t0: number | null } | null = null;
  const aplicar = (p: PoseCamara) => {
    camera.position.copy(p.posicion);
    controls.target.copy(p.objetivo);
    controls.update();
  };
  const cancelar = () => { vuelo = null; };
  controls.addEventListener?.("start", cancelar); // la persona tomó la cámara
  return {
    volar: (destino, duracionMs = MOV_NORMAL_MS) => {
      if (reducido() || !(duracionMs > 0)) {
        vuelo = null;
        aplicar(destino);
        return;
      }
      const desde = { posicion: camera.position.clone(), objetivo: controls.target.clone() };
      vuelo = { desde, hasta: destino, dur: duracionMs, t0: null }; // arranca en el próximo cuadro
    },
    tick: (ahora) => {
      if (!vuelo) return;
      if (vuelo.t0 === null) vuelo.t0 = ahora;
      const f = Math.min(1, (ahora - vuelo.t0) / vuelo.dur);
      const v = vuelo;
      if (f >= 1) vuelo = null;
      aplicar(f >= 1 ? v.hasta : poseEn(v.desde, v.hasta, suave(f)));
    },
    cancelar,
    enCurso: () => vuelo !== null,
    dispose: () => controls.removeEventListener?.("start", cancelar),
  };
}
