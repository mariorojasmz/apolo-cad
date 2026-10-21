import type * as THREE from "three";
import type { Pipeline } from "../../pipeline";
import { crearEscenaTrazable, estudioCubo } from "./escenaTrazable";
import type { OpcionesTrazado } from "./nivel";
import { crearTrazador, type ControlTrazado, type InformeTrazado } from "./trazador";

/* El nivel máximo armado sobre el pipeline del visor: el trazador + la escena trazable. Se carga
   con `import()` la primera vez que se pide (`modo.ts`): `three-gpu-pathtracer` y
   `three-mesh-bvh` no pesan en el visor de todos los días. */

export interface NivelMaximo {
  /** Traza el cuadro ya preparado (`prepararCuadro`) y lo deja en el canvas. */
  cuadro: (op: OpcionesTrazado, ctl: ControlTrazado) => Promise<InformeTrazado>;
  dispose: () => void;
}

export function crearNivelMaximo(pipe: Pipeline): NivelMaximo {
  const trazador = crearTrazador(pipe.renderer);
  const escena = crearEscenaTrazable(pipe.scene, pipe.group,
    pipe.ground.userData.estudio as THREE.Object3D | undefined, estudioCubo(pipe.renderer));
  return {
    cuadro: async (op, ctl) => {
      const deshacer = escena.preparar();
      try {
        return await trazador.trazar(pipe.scene, pipe.camera, op, ctl);
      } finally {
        deshacer(); // no dibuja: el canvas sigue con el cuadro trazado para la foto
      }
    },
    dispose: () => {
      trazador.dispose();
      escena.dispose();
    },
  };
}
