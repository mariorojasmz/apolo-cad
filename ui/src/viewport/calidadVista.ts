import * as THREE from "three";
import type { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { GTAOPass } from "three/examples/jsm/postprocessing/GTAOPass.js";
import { SMAAPass } from "three/examples/jsm/postprocessing/SMAAPass.js";
import type { Calidad } from "./calidad";
import { materialesDe } from "./zonas";

/* Los pases de la calidad «alta» del visor (video-realista D1) y el interruptor que los prende:
   - GTAO (oclusión ambiental): oscurece rincones y encuentros entre piezas. Hace una SEGUNDA
     pasada de la escena (normales + profundidad): en F0 era lo caro (con 1 M de triángulos manda
     el vértice), así que sólo dibuja la máquina (`group`) y sin aristas.
   - SMAA, al final de la cadena (después de `OutputPass`, sobre sRGB).
   - Sin MSAA en el render target: SMAA lo reemplaza y es lo que paga el GTAO (F0: de 13 a ~20 fps
     en una Intel UHD). En «normal» vuelve el MSAA ×4 y los dos pases se apagan: el visor de antes.

   El radio del GTAO va en mm y sigue el tamaño de la máquina; lo recalcula `ajustar` (≤ 3 veces
   por segundo, sólo en «alta»), que también copia los planos de sección al material de normales
   (si no, la oclusión saldría de la pieza ENTERA con el corte puesto). */

/** Muestras de MSAA del render target del composer en cada calidad. */
export const MSAA: Record<Calidad, number> = { alta: 0, normal: 4 };
/** Radio y grosor de la oclusión como fracción de la diagonal de la máquina (calibrado en F0/F1). */
export const RADIO_FRACCION = 0.02;
export const GROSOR_FRACCION = 0.01;
export const RADIO_MIN_MM = 5;
/** Cada cuánto se reajusta el radio a la máquina y los planos de sección (ms). */
export const INTERVALO_AJUSTE_MS = 300;

/** Radio y grosor (mm) de la oclusión para una máquina de diagonal `diagonal` mm. */
export function escalaOclusion(diagonal: number): { radio: number; grosor: number } {
  const radio = Math.max(diagonal * RADIO_FRACCION, RADIO_MIN_MM);
  return { radio, grosor: Math.max(diagonal * GROSOR_FRACCION, RADIO_MIN_MM / 2) };
}

/** GTAO que sólo ve la máquina: todo lo demás de la escena (piso, grilla, gizmo, tiradores,
   medidas, cajas) y las aristas quedan fuera de la pasada de normales. */
export class GtaoMaquina extends GTAOPass {
  private readonly ocultos: THREE.Object3D[] = [];
  constructor(scene: THREE.Scene, camera: THREE.Camera, private readonly maquina: THREE.Object3D) {
    super(scene, camera, 1, 1);
  }

  override overrideVisibility(): void {
    const ocultar = (o: THREE.Object3D) => {
      if (o.visible) {
        o.visible = false;
        this.ocultos.push(o);
      }
    };
    for (const hijo of this.scene.children) if (hijo !== this.maquina) ocultar(hijo);
    this.maquina.traverse((o) => {
      const x = o as THREE.Object3D & { isLine?: boolean; isPoints?: boolean; isSprite?: boolean };
      if (x.isLine || x.isPoints || x.isSprite) ocultar(o);
    });
  }

  override restoreVisibility(): void {
    for (const o of this.ocultos) o.visible = true;
    this.ocultos.length = 0;
  }
}

export interface CalidadVista {
  gtao: GtaoMaquina;
  smaa: SMAAPass;
  calidad: () => Calidad;
  /** Prende o apaga los pases y cambia el MSAA del composer. */
  fijar: (calidad: Calidad) => void;
  /** Tarea por cuadro (antes de componer): reajusta radio y planos de sección, con tope. */
  ajustar: (ahora: number) => void;
  dispose: () => void;
}

export function crearCalidadVista(
  scene: THREE.Scene, camera: THREE.Camera, maquina: THREE.Object3D, composer: EffectComposer,
): CalidadVista {
  const gtao = new GtaoMaquina(scene, camera, maquina);
  gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 6, rings: 2, samples: 16 });
  const smaa = new SMAAPass(1, 1);
  let actual: Calidad = "normal";
  let ultimo = -Infinity;
  const caja = new THREE.Box3();

  const fijar = (calidad: Calidad) => {
    actual = calidad;
    gtao.enabled = calidad === "alta";
    smaa.enabled = calidad === "alta";
    for (const rt of [composer.renderTarget1, composer.renderTarget2]) {
      if (rt.samples !== MSAA[calidad]) {
        rt.samples = MSAA[calidad];
        rt.dispose(); // se vuelve a reservar con las muestras nuevas en el próximo cuadro
      }
    }
    ultimo = -Infinity; // reajusta ya
  };

  const ajustar = (ahora: number) => {
    if (actual !== "alta" || ahora - ultimo < INTERVALO_AJUSTE_MS) return;
    ultimo = ahora;
    caja.setFromObject(maquina);
    if (caja.isEmpty()) return;
    const { radio, grosor } = escalaOclusion(caja.getSize(new THREE.Vector3()).length());
    gtao.updateGtaoMaterial({ radius: radio, thickness: grosor, distanceExponent: 1, scale: 1, samples: 16 });
    gtao.setSceneClipBox(caja.expandByScalar(radio * 2));
    // planos de sección: los mismos que llevan los materiales de las piezas
    const malla = maquina.children.find((o) => (o as THREE.Mesh).isMesh) as THREE.Mesh | undefined;
    const planos = materialesDe(malla?.material)[0]?.clippingPlanes ?? null; // con zonas, un arreglo
    if (gtao.normalMaterial.clippingPlanes !== planos) gtao.normalMaterial.clippingPlanes = planos;
  };

  return {
    gtao, smaa, fijar, ajustar,
    calidad: () => actual,
    dispose: () => {
      gtao.dispose();
      smaa.dispose();
    },
  };
}
