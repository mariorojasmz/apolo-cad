import type * as THREE from "three";
import { useCalidad } from "../calidad";
import type { Pipeline } from "../pipeline";
import { PaseAcumulado } from "./acumulado";
import type { NivelMaximo } from "./trazado/maximo";
import { opcionesTrazado, TRAZADO_VIDEO, type Nivel, type OpcionesTrazado } from "./trazado/nivel";
import type { ControlTrazado, InformeTrazado } from "./trazado/trazador";

/* Modo grabación del visor (plan video-realista, D3). Mientras dura:
   - el render tiene tamaño FIJO (1920×1080 por defecto, 3840×2160 opcional) con DPR 1 y el bucle
     de `requestAnimationFrame` está parado: cada cuadro lo pide el reloj virtual con `cuadro(ms)`;
   - la calidad es «alta» (estudio + GTAO) sin tocar lo que eligió la persona, y el antialias es
     el ACUMULADO (`acumulado.ts`) en vez del SMAA y del MSAA;
   - no salen la grilla, los ejes, el gizmo, los tiradores, el contorno de selección ni el
     destello del agente, ni el ViewCube.
   Con el nivel MÁXIMO (D6, F4) cada cuadro lo traza `trazado/trazador.ts` sobre la misma escena
   (`trazado/escenaTrazable.ts`) en vez del acumulado + GTAO.
   `salir` deja el visor exactamente como estaba. */

/** Muestras del antialias por cuadro en el nivel rápido, y cuántas se dibujan por tanda. */
export const MUESTRAS_RAPIDO = 16;
export const MUESTRAS_POR_TANDA = 4;

/** Lo que un cuadro puede pedir aparte del reloj (sólo lo usa el nivel máximo). */
export interface ExtraCuadro extends ControlTrazado {
  semilla?: number;
}

export interface ModoGrabacion {
  nivel: Nivel;
  /** Dibuja el cuadro del instante `ms` con todas sus muestras; al volver, el canvas lo tiene.
     En el nivel máximo devuelve los tiempos del trazado. */
  cuadro: (ms: number, extra?: ExtraCuadro) => Promise<InformeTrazado | null>;
  salir: () => void;
}

/** Suelta el hilo sin depender de timers ni de rAF (los dos se frenan con la pestaña de fondo). */
export function ceder(): Promise<void> {
  return new Promise((res) => {
    const canal = new MessageChannel();
    canal.port1.onmessage = () => {
      canal.port1.close();
      res();
    };
    canal.port2.postMessage(null);
  });
}

export interface OpcionesModo {
  ancho: number;
  alto: number;
  /** Muestras del antialias del nivel rápido. */
  muestras?: number;
  ocultar?: THREE.Object3D[];
  nivel?: Nivel;
  /** Opciones del trazado (nivel máximo); por defecto, las del video. */
  trazado?: OpcionesTrazado;
}

export function entrarModoGrabacion(pipe: Pipeline, op: OpcionesModo): ModoGrabacion {
  const { composer, pases, renderer, scene, camera, calidad } = pipe;
  const nivel: Nivel = op.nivel ?? "rapido";
  const ocultos = [...pipe.ayudantes, ...(op.ocultar ?? [])].filter((o) => o.visible);
  const camaraAntes = { pos: camera.position.clone(), target: pipe.controls.target.clone() };
  const acumulado = nivel === "rapido" ? new PaseAcumulado(scene, camera) : null;
  const trazado = nivel === "maximo" ? (op.trazado ?? opcionesTrazado(TRAZADO_VIDEO)) : null;
  // el trazador se carga aparte (`import()`) y se arma en el primer cuadro
  let maximo: NivelMaximo | null = null;
  const armarMaximo = async () => {
    maximo ??= (await import("./trazado/maximo")).crearNivelMaximo(pipe);
    return maximo;
  };
  if (acumulado) acumulado.muestras = Math.max(1, Math.round(op.muestras ?? MUESTRAS_RAPIDO));

  pipe.modoGrabacion({ ancho: op.ancho, alto: op.alto });
  pipe.aplicarCalidad("alta");
  for (const o of ocultos) o.visible = false;
  const apagados = [pases.render, pases.contorno, pases.destello];
  const antes = apagados.map((p) => p.enabled);
  const apagar = () => {
    for (const p of apagados) p.enabled = false;
    calidad.smaa.enabled = false;
  };
  apagar();
  if (acumulado) {
    composer.insertPass(acumulado, 1);
    acumulado.setSize(op.ancho, op.alto);
  }

  let fuera = false;
  return {
    nivel,
    cuadro: async (ms, extra = {}) => {
      if (trazado) {
        const m = await armarMaximo();
        if (fuera) throw new Error("La grabación ya terminó.");
        pipe.prepararCuadro(ms);
        return m.cuadro({ ...trazado, semilla: extra.semilla ?? trazado.semilla }, extra);
      }
      pipe.prepararCuadro(ms);
      apagar(); // el destello se prende solo al actualizarse, y el SMAA si cambian la calidad
      acumulado!.reiniciar();
      while (!acumulado!.listo) {
        acumulado!.acumular(renderer, MUESTRAS_POR_TANDA);
        if (!acumulado!.listo) await ceder();
      }
      pipe.componer(); // GTAO + OutputPass sobre el promedio; el llamador toma la foto YA
      return null;
    },
    salir: () => {
      if (fuera) return;
      fuera = true;
      if (acumulado) {
        composer.removePass(acumulado);
        acumulado.dispose();
      }
      maximo?.dispose();
      apagados.forEach((p, i) => { p.enabled = antes[i]; });
      for (const o of ocultos) o.visible = true;
      camera.position.copy(camaraAntes.pos);
      pipe.controls.target.copy(camaraAntes.target);
      pipe.aplicarCalidad(useCalidad.getState().calidad);
      pipe.modoGrabacion(null);
    },
  };
}
