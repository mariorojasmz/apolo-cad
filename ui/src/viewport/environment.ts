import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import type { Calidad } from "./calidad";
import { SIGMA, crearEstudio, liberarEscena } from "./estudio";

/* Luz de ambiente por imagen (IBL), generada proceduralmente (sin assets externos → compatible
   con CSP). Da a los metales algo que reflejar; sin esto el PBR queda lavado. Solo afecta a los
   reflejos (scene.environment), NO al fondo (lo pinta el <div> por CSS).

   Dos según la calidad (video-realista D1): «normal» = RoomEnvironment (el visor de siempre);
   «alta» = el estudio con softboxes (`estudio.ts`). Cada uno se arma una vez, la primera vez que
   se pide (el PMREM no cuesta por cuadro). */

export interface Entorno {
  fijar: (calidad: Calidad) => void;
  dispose: () => void;
}

export function crearEntorno(renderer: THREE.WebGLRenderer, scene: THREE.Scene): Entorno {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const mapas = new Map<Calidad, THREE.Texture>();
  const armar = (calidad: Calidad): THREE.Texture => {
    const escena = calidad === "alta" ? crearEstudio() : new RoomEnvironment();
    const tex = pmrem.fromScene(escena, calidad === "alta" ? SIGMA : 0.04).texture;
    liberarEscena(escena);
    return tex;
  };
  return {
    fijar: (calidad) => {
      let tex = mapas.get(calidad);
      if (!tex) {
        tex = armar(calidad);
        mapas.set(calidad, tex);
      }
      scene.environment = tex;
    },
    dispose: () => {
      scene.environment = null;
      for (const tex of mapas.values()) tex.dispose();
      mapas.clear();
      pmrem.dispose();
    },
  };
}
