import * as THREE from "three";
import { DenoiseMaterial, GradientEquirectTexture, WebGLPathTracer } from "three-gpu-pathtracer";
import { FullScreenQuad } from "three/examples/jsm/postprocessing/Pass.js";
import { GrabacionCancelada } from "../reloj";
import { aleatorioConSemilla, type OpcionesTrazado } from "./nivel";

/* El nivel MÁXIMO (plan video-realista, D6): trazado de rayos de un cuadro con
   `three-gpu-pathtracer` 0.0.23 (MIT, WebGL2; la última que acepta three 0.169, F0) sobre la
   escena que deja `escenaTrazable.ts`. Por cuadro:

   1. `setScene` es INCREMENTAL: si sólo se movió la cámara no toca la geometría; si se movieron
      mallas (la marcha) reajusta el BVH (refit); si entran o salen piezas (el montaje), lo rearma.
   2. N muestras con la semilla del cuadro, en teselas, sincronizando la GPU tras cada pedazo (una
      llamada larga reinicia el driver) y soltando el hilo entre pedazos.
   3. El denoiser de la librería (`DenoiseMaterial`, glslSmartDeNoise) pinta el canvas con el
      MISMO tonemapping (ACES) y espacio de color (sRGB) que el `OutputPass` del visor.

   Se usa lo de ADENTRO de `WebGLPathTracer` (`_pathTracer`) para lo que la API pública no da:
   fijar la semilla, el tamaño y el fondo transparente sin el reloj de `renderSample`. La versión
   está fijada EXACTA en `package.json`: subirla exige revisar `Interno`.

   Determinismo: con `stableNoise` el muestreo estratificado sale de un generador con semilla; el
   desplazamiento por píxel (ruido azul, que la librería arma con `Math.random`) se rehace una vez
   con un aleatorio con semilla fija. Misma pose + misma semilla → misma imagen (lo mide F4). */

interface Interno {
  _pathTracer: {
    material: THREE.ShaderMaterial & {
      seed: number;
      bounces: number;
      transmissiveBounces: number;
      backgroundMap: THREE.Texture | null;
      backgroundAlpha: number;
      stratifiedTexture: { generator: { seed: number }; init: (n: number, d: number) => void; reset: () => void };
      stratifiedOffsetTexture: THREE.DataTexture & { update: () => void };
    };
    samples: number;
    tiles: THREE.Vector2;
    stableNoise: boolean;
    alpha: boolean;
    isCompiling: boolean;
    target: THREE.WebGLRenderTarget;
    setSize: (w: number, h: number) => void;
    reset: () => void;
    update: () => void;
    dispose: () => void;
  };
  _lowResPathTracer: { dispose: () => void };
  _quad: FullScreenQuad;
  _generator: { geometry: THREE.BufferGeometry };
}

/** Semilla del ruido azul por píxel (no cambia con la semilla del cuadro). */
const SEMILLA_RUIDO_AZUL = 20261021;
/** Tope para compilar el shader del trazador. */
const COMPILAR_MAX_MS = 300_000;

/** El `DenoiseMaterial` de la librería espera color SIN premultiplicar, pero con fondo
   transparente el acumulado ya está premultiplicado (el fondo aporta 0 de color y 0 de alfa):
   se le quita su premultiplicado, se despremultiplica antes del tonemapping y se vuelve a
   premultiplicar al final (el canvas es `premultipliedAlpha`). Falla si la librería cambió. */
export function adaptarDenoise(mat: THREE.ShaderMaterial): void {
  const cambios: [string, string][] = [
    ["centrPx.rgb *= centrPx.a;", ""],
    ["walkPx.rgb *= walkPx.a;", ""],
    ["gl_FragColor = smartDeNoise( map, vec2( vUv.x, vUv.y ), sigma, kSigma, threshold );",
      "gl_FragColor = smartDeNoise( map, vec2( vUv.x, vUv.y ), sigma, kSigma, threshold );\n"
      + "gl_FragColor.rgb /= max( gl_FragColor.a, 1e-4 );"],
    ["#include <premultiplied_alpha_fragment>", "gl_FragColor.rgb *= gl_FragColor.a;"],
  ];
  let fs = mat.fragmentShader;
  for (const [de, a] of cambios) {
    if (!fs.includes(de)) throw new Error(`El denoiser de three-gpu-pathtracer cambió: falta «${de}».`);
    fs = fs.replace(de, a);
  }
  mat.fragmentShader = fs;
  mat.needsUpdate = true;
}

export interface InformeTrazado {
  muestras: number;
  /** Segundos preparando la escena (BVH, materiales, luces) y trazando las muestras. */
  segundosEscena: number;
  segundosMuestras: number;
  ancho: number;
  alto: number;
}

export interface ControlTrazado {
  progreso?: (hechas: number, total: number) => void;
  cancelado?: () => boolean;
}

export interface Trazador {
  /** Traza `scene` desde `camera` y deja la imagen en el canvas (el llamador la fotografía en el
     mismo hilo, sin soltarlo). */
  trazar: (scene: THREE.Scene, camera: THREE.Camera, op: OpcionesTrazado, ctl?: ControlTrazado) => Promise<InformeTrazado>;
  dispose: () => void;
}

/** Suelta el hilo sin depender de timers ni de rAF (los dos se frenan con la pestaña de fondo). */
function ceder(): Promise<void> {
  return new Promise((res) => {
    const canal = new MessageChannel();
    canal.port1.onmessage = () => {
      canal.port1.close();
      res();
    };
    canal.port2.postMessage(null);
  });
}

const dormir = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function crearTrazador(renderer: THREE.WebGLRenderer): Trazador {
  const pt = new WebGLPathTracer(renderer);
  const interno = pt as unknown as Interno;
  const nucleo = interno._pathTracer;
  pt.renderToCanvas = false;
  pt.rasterizeScene = false;
  pt.synchronizeRenderSize = false;
  pt.dynamicLowRes = false;
  pt.renderDelay = 0;
  pt.minSamples = 0;
  pt.fadeDuration = 0;
  pt.textureSize.set(256, 256); // las texturas procedurales son de 128 px (`relieve.ts::LADO`)
  nucleo.stableNoise = true;
  // el ruido azul por píxel, con semilla fija (la librería lo arma con Math.random)
  const azar = Math.random;
  Math.random = aleatorioConSemilla(SEMILLA_RUIDO_AZUL);
  try {
    nucleo.material.stratifiedOffsetTexture.update();
  } finally {
    Math.random = azar;
  }
  const fondo = new GradientEquirectTexture(4); // negro: el fondo no aporta color al acumulado
  fondo.topColor.set(0x000000);
  fondo.bottomColor.set(0x000000);
  fondo.update();
  const salida = new DenoiseMaterial();
  adaptarDenoise(salida);
  const quad = new FullScreenQuad(salida);
  const tam = new THREE.Vector2();
  const px = new Float32Array(4);
  const color = new THREE.Color();

  const sincronizar = () => // espera a la GPU: un pedazo por vez, sin colas de segundos
    renderer.readRenderTargetPixels(nucleo.target, 0, 0, 1, 1, px);

  return {
    trazar: async (scene, camera, op, ctl = {}) => {
      const t0 = performance.now();
      pt.bounces = op.rebotes;
      // la 0.0.23 SUMA los grupos de la geometría unida en cada `setScene` sin vaciarlos: en un
      // video de 2 000 cuadros el índice de materiales se rehacía sobre cientos de miles
      interno._generator.geometry.clearGroups();
      pt.setScene(scene, camera); // incremental (ver arriba)
      const mat = nucleo.material;
      mat.backgroundMap = fondo; // después de setScene: `updateEnvironment` los pisa
      mat.backgroundAlpha = 0;
      renderer.getDrawingBufferSize(tam);
      nucleo.setSize(tam.x, tam.y);
      nucleo.tiles.set(op.teselas, op.teselas);
      nucleo.alpha = true;
      nucleo.reset();
      // el muestreo estratificado con su tamaño final ANTES de sembrar: si lo armara la primera
      // muestra, gastaría números del generador y el primer cuadro no se repetiría
      const estr = mat.stratifiedTexture;
      estr.init(20, mat.bounces + mat.transmissiveBounces + 5);
      estr.reset();
      mat.seed = op.semilla;
      estr.generator.seed = op.semilla;
      const t1 = performance.now();
      const porMuestra = op.teselas * op.teselas;
      let pedazos = 0;
      while (nucleo.samples < op.muestras) {
        if (ctl.cancelado?.()) throw new GrabacionCancelada();
        nucleo.update();
        if (nucleo.isCompiling) {
          // la primera vez compila el shader del trazador (largo en una GPU integrada)
          if (performance.now() - t1 > COMPILAR_MAX_MS) {
            throw new Error("La GPU no terminó de preparar el trazado de rayos: prueba en otra PC.");
          }
          await dormir(50);
          continue;
        }
        sincronizar();
        if (++pedazos % porMuestra === 0) ctl.progreso?.(Math.round(nucleo.samples), op.muestras);
        await ceder();
      }
      const t2 = performance.now();
      // al canvas: el denoiser (sin él, kSigma 0 = el acumulado tal cual) + ACES + sRGB
      const d = op.denoise;
      salida.uniforms.map.value = nucleo.target.texture;
      salida.uniforms.sigma.value = d?.sigma ?? 1;
      salida.uniforms.kSigma.value = d ? d.kSigma : 0;
      salida.uniforms.threshold.value = d?.umbral ?? 1;
      const previo = renderer.getRenderTarget();
      const alfa = renderer.getClearAlpha();
      renderer.getClearColor(color);
      renderer.setRenderTarget(null);
      renderer.setClearColor(0x000000, 0);
      renderer.clear();
      quad.render(renderer);
      renderer.setClearColor(color, alfa);
      renderer.setRenderTarget(previo);
      return {
        muestras: Math.round(nucleo.samples), ancho: tam.x, alto: tam.y,
        segundosEscena: (t1 - t0) / 1000, segundosMuestras: (t2 - t1) / 1000,
      };
    },
    dispose: () => {
      // `WebGLPathTracer.dispose` de la 0.0.23 se cae (`_renderQuad` no existe): a mano
      for (const liberar of [
        () => nucleo.dispose(), () => interno._lowResPathTracer.dispose(),
        () => interno._quad.dispose(), () => interno._generator.geometry.dispose(),
        () => fondo.dispose(), () => salida.dispose(), () => quad.dispose(),
      ]) {
        try { liberar(); } catch { /* best-effort */ }
      }
    },
  };
}
