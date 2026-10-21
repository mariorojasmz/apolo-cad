import * as THREE from "three";
import { crearEstudio, liberarEscena } from "../../estudio";
import { PISO_ESTUDIO_COLOR } from "../../scene-setup";
import { Sustitutos } from "./sustitutos";

/* La escena del visor, lista para el trazador (plan video-realista, F4). El trazado usa la MISMA
   escena, cámara y materiales que el visor «alta»; lo que cambia es lo que el trazador no sabe
   dibujar y su reemplazo:

   - El IBL del visor es un PMREM (no lo lee el trazador): el MISMO estudio procedural
     (`estudio.ts`) se dibuja a un cubo HDR, que el trazador pasa a equirectangular (y arma su
     muestreo por importancia) la primera vez que lo ve.
   - El piso del visor es un `ShadowMaterial` + un disco con shader propio, y la sombra de contacto
     es un truco de raster: en el trazado los reemplaza un disco de verdad con el color y la caída
     de opacidad del de `scene-setup.ts`; la sombra y el contacto salen del trazado.
   - Sólo entran `group` (la máquina, con la marcha y sus cadenas) y las luces: grilla, ejes, gizmo,
     tiradores, medida, la sombra de contacto y las cajas del drop-test quedan fuera.
   - Las cadenas instanciadas y las piezas con zonas entran como mallas SUSTITUTAS de un solo
     material (`sustitutos.ts`): la librería no sabe de instancias ni de arreglos de materiales.

   `preparar()` aplica todo eso y devuelve cómo deshacerlo; entre cuadros no se toca nada. */

/** Opacidad del disco del piso según el radio relativo (0 centro … 1 borde): el shader de
   `scene-setup.ts::crearPisoEstudio`. */
export function alfaPiso(r: number): number {
  const x = Math.min(Math.max((r - 0.15) / 0.85, 0), 1);
  return (1 - x * x * (3 - 2 * x)) * 0.9;
}

/** Lado de la textura de la caída de opacidad del disco. */
const LADO_ALFA = 128;

function texturaAlfaPiso(): THREE.DataTexture {
  const datos = new Uint8Array(LADO_ALFA * LADO_ALFA * 4);
  for (let j = 0; j < LADO_ALFA; j++) {
    for (let i = 0; i < LADO_ALFA; i++) {
      const u = (i + 0.5) / LADO_ALFA - 0.5;
      const v = (j + 0.5) / LADO_ALFA - 0.5;
      const a = Math.round(alfaPiso(Math.hypot(u, v) * 2) * 255);
      const k = (j * LADO_ALFA + i) * 4;
      datos[k] = datos[k + 1] = datos[k + 2] = a;
      datos[k + 3] = 255;
    }
  }
  const tex = new THREE.DataTexture(datos, LADO_ALFA, LADO_ALFA, THREE.RGBAFormat);
  tex.colorSpace = THREE.NoColorSpace;
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearFilter;
  tex.needsUpdate = true;
  return tex;
}

/** El estudio procedural del visor «alta» en un cubo HDR (el trazador lo pasa a equirectangular). */
export function estudioCubo(renderer: THREE.WebGLRenderer, lado = 256): THREE.WebGLCubeRenderTarget {
  const escena = crearEstudio();
  const rt = new THREE.WebGLCubeRenderTarget(lado, { type: THREE.HalfFloatType });
  const cubo = new THREE.CubeCamera(0.1, 100, rt);
  const previo = renderer.getRenderTarget();
  cubo.update(renderer, escena);
  renderer.setRenderTarget(previo);
  liberarEscena(escena);
  return rt;
}

export interface EscenaTrazable {
  /** Deja la escena como la ve el trazador; devuelve cómo volver al visor. */
  preparar: () => () => void;
  dispose: () => void;
}

/** `estudio` = el disco del piso del visor (`ground.userData.estudio`), que da dónde y de qué
   tamaño va el piso del trazado. `entorno` = el cubo del estudio (`estudioCubo`). */
export function crearEscenaTrazable(scene: THREE.Scene, group: THREE.Object3D,
  estudio: THREE.Object3D | undefined, entorno: THREE.WebGLCubeRenderTarget | null): EscenaTrazable {
  const alfa = texturaAlfaPiso();
  const piso = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshStandardMaterial({
    color: PISO_ESTUDIO_COLOR, roughness: 0.92, metalness: 0, transparent: true, alphaMap: alfa,
  }));
  piso.name = "piso-trazado";
  const sustitutos = new Sustitutos();
  return {
    preparar: () => {
      const ocultos: THREE.Object3D[] = [];
      for (const o of scene.children) {
        const queda = o === group || (o as THREE.Light).isLight;
        if (!queda && o.visible) {
          o.visible = false;
          ocultos.push(o);
        }
      }
      if (estudio) {
        estudio.updateMatrixWorld();
        estudio.matrixWorld.decompose(piso.position, piso.quaternion, piso.scale);
      }
      piso.visible = !!estudio;
      scene.add(piso, sustitutos.grupo);
      const originales = sustitutos.sincronizar(group);
      for (const o of originales) o.visible = false;
      const antes = { environment: scene.environment, background: scene.background };
      scene.environment = entorno?.texture ?? null;
      scene.background = null;
      return () => {
        scene.environment = antes.environment;
        scene.background = antes.background;
        for (const o of originales) o.visible = true;
        scene.remove(piso, sustitutos.grupo);
        for (const o of ocultos) o.visible = true;
      };
    },
    dispose: () => {
      piso.geometry.dispose();
      (piso.material as THREE.Material).dispose();
      alfa.dispose();
      entorno?.dispose();
      sustitutos.dispose();
    },
  };
}
