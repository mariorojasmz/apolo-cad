import * as THREE from "three";
import { encuadreGiro } from "./encuadre";
import type { Pipeline } from "../pipeline";
import { useMarcha } from "../marcha/estado";
import { crearCaptura } from "./captura";
import { grabarVideo, type AperturaGrabacion, type FormatoCuadro, type ResultadoVideo } from "./grabador";
import { planGiro, posicionGiro, tiempoMarcha } from "./guion";
import { entrarModoGrabacion, MUESTRAS_RAPIDO } from "./modo";
import { opcionesTrazado, semillaDeCuadro, TRAZADO_VIDEO, type Nivel, type OpcionesTrazado } from "./trazado/nivel";

/* La grabación dentro del visor (plan video-realista, F2): junta el modo grabación (tamaño fijo,
   antialias acumulado), el reloj virtual, el guion del giro con la marcha y el cliente que sube
   los cuadros a la API. `Viewport.tsx` la instala sobre su pipeline y la publica en
   `window.__apolo.grabar` (el botón «Grabar video» y el modo sin ventana son de F3). */

export interface OpcionesGrabar {
  fps?: number;
  ancho?: number;
  alto?: number;
  formato?: FormatoCuadro;
  /** Muestras de antialias por cuadro (nivel rápido: 16). */
  muestras?: number;
  /** «rapido» (por defecto) o «maximo»: trazado de rayos por cuadro (D6), horas por video. */
  nivel?: Nivel;
  /** Opciones del trazado del nivel máximo (muestras, semilla…), sobre las del video. */
  trazado?: Partial<OpcionesTrazado>;
  /** Duración (s); por defecto, la de la marcha cargada o un giro de 8 s. */
  segundos?: number;
  grados?: number;
  /** Acercar la cámara para que la máquina llene el cuadro en todo el giro (por defecto, sí). */
  encuadrar?: boolean;
  musica?: string;
  salida?: string;
  conservarCuadros?: boolean;
  /** Grabar aunque el navegador dibuje sin GPU (horas en vez de minutos). */
  permitirSinGpu?: boolean;
  progreso?: (avance: { dibujados: number; subidos: number; total: number }) => void;
  alAbrir?: (apertura: AperturaGrabacion) => void;
}

export interface InformeGrabacion extends ResultadoVideo {
  gpu: string | null;
  /** Segundos por cuadro dibujando, codificando la foto y subiéndola (sin el MP4). */
  segundosPorCuadro: number;
}

/** El nombre de la GPU con que dibuja este navegador (`null` si no lo dice). */
export function nombreGpu(renderer: THREE.WebGLRenderer): string | null {
  const gl = renderer.getContext();
  const info = gl.getExtension("WEBGL_debug_renderer_info");
  return info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : null;
}

/** Sin GPU de verdad (SwiftShader, llvmpipe…) el nivel rápido tardaría horas. */
export const sinGpu = (nombre: string | null) =>
  !!nombre && /swiftshader|llvmpipe|software|basic render/i.test(nombre);

export function crearGrabacionVista(pipe: Pipeline, ocultar: () => THREE.Object3D[]) {
  let grabando = false;
  return async function grabar(op: OpcionesGrabar = {}): Promise<InformeGrabacion> {
    if (grabando) throw new Error("Ya hay una grabación en curso: espera a que termine.");
    const gpu = nombreGpu(pipe.renderer);
    if (sinGpu(gpu) && !op.permitirSinGpu) {
      throw new Error("Este navegador dibuja sin GPU y el video tardaría horas. Abre Apolo en un "
        + "navegador con aceleración por hardware.");
    }
    grabando = true;
    const fps = op.fps ?? 30;
    const ancho = op.ancho ?? 1920;
    const alto = op.alto ?? 1080;
    const formato = op.formato ?? "jpeg";
    const marcha = useMarcha.getState();
    const serie = marcha.serie && marcha.serie.t.length > 1 ? marcha.serie : null;
    const plan = planGiro({ fps, marchaSegundos: serie?.duracion_s ?? null, segundos: op.segundos,
      grados: op.grados });
    const antes = { reproduciendo: marcha.reproduciendo, t: marcha.t };
    if (serie) useMarcha.setState({ reproduciendo: false });

    const { camera, controls } = pipe;
    const trazado = opcionesTrazado(TRAZADO_VIDEO, op.trazado);
    const modo = entrarModoGrabacion(pipe, { ancho, alto, muestras: op.muestras ?? MUESTRAS_RAPIDO,
      ocultar: ocultar(), nivel: op.nivel, trazado });
    // ya con el aspecto del video: la máquina entra justa en el cuadro durante todo el giro
    const encuadre = op.encuadrar === false ? null
      : encuadreGiro(camera, controls.target, new THREE.Box3().setFromObject(pipe.group), plan.grados);
    if (encuadre) {
      camera.position.copy(encuadre.posicion);
      controls.target.copy(encuadre.objetivo);
    }
    const objetivo = controls.target.toArray() as [number, number, number];
    const desde = camera.position.toArray() as [number, number, number];
    const captura = crearCaptura(ancho, alto, formato);
    try {
      const r = await grabarVideo({
        ancho, alto, fps, formato, cuadros: plan.cuadros,
        musica: op.musica, salida: op.salida, conservarCuadros: op.conservarCuadros,
        progreso: op.progreso, alAbrir: op.alAbrir,
        dibujar: async (n, ms) => {
          if (serie) useMarcha.getState().saltar(tiempoMarcha(plan, n)); // lo consume el reproductor
          camera.position.fromArray(posicionGiro(objetivo, desde, plan, n));
          camera.lookAt(controls.target);
          await modo.cuadro(ms, { semilla: semillaDeCuadro(trazado, n) });
          return captura.tomar(pipe.renderer.domElement); // en el mismo hilo que el render
        },
      });
      return { ...r, gpu, segundosPorCuadro: r.segundosCuadros / plan.cuadros };
    } finally {
      modo.salir();
      if (serie) {
        useMarcha.setState({ reproduciendo: antes.reproduciendo });
        useMarcha.getState().saltar(antes.t);
      }
      grabando = false;
    }
  };
}
