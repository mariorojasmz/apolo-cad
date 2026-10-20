import type * as THREE from "three";
import { useCalidad } from "../calidad";
import type { Pipeline } from "../pipeline";
import { PaseAcumulado } from "./acumulado";

/* Modo grabación del visor (plan video-realista, D3). Mientras dura:
   - el render tiene tamaño FIJO (1920×1080 por defecto, 3840×2160 opcional) con DPR 1 y el bucle
     de `requestAnimationFrame` está parado: cada cuadro lo pide el reloj virtual con `cuadro(ms)`;
   - la calidad es «alta» (estudio + GTAO) sin tocar lo que eligió la persona, y el antialias es
     el ACUMULADO (`acumulado.ts`) en vez del SMAA y del MSAA;
   - no salen la grilla, los ejes, el gizmo, los tiradores, el contorno de selección ni el
     destello del agente, ni el ViewCube.
   `salir` deja el visor exactamente como estaba. */

/** Muestras del antialias por cuadro en el nivel rápido, y cuántas se dibujan por tanda. */
export const MUESTRAS_RAPIDO = 16;
export const MUESTRAS_POR_TANDA = 4;

export interface ModoGrabacion {
  /** Dibuja el cuadro del instante `ms` con todas sus muestras; al volver, el canvas lo tiene. */
  cuadro: (ms: number) => Promise<void>;
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

export function entrarModoGrabacion(pipe: Pipeline, op: {
  ancho: number; alto: number; muestras?: number; ocultar?: THREE.Object3D[];
}): ModoGrabacion {
  const { composer, pases, renderer, scene, camera, calidad } = pipe;
  const ocultos = [...pipe.ayudantes, ...(op.ocultar ?? [])].filter((o) => o.visible);
  const camaraAntes = { pos: camera.position.clone(), target: pipe.controls.target.clone() };
  const acumulado = new PaseAcumulado(scene, camera);
  acumulado.muestras = Math.max(1, Math.round(op.muestras ?? MUESTRAS_RAPIDO));

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
  composer.insertPass(acumulado, 1);
  acumulado.setSize(op.ancho, op.alto);

  let fuera = false;
  return {
    cuadro: async (ms) => {
      pipe.prepararCuadro(ms);
      apagar(); // el destello se prende solo al actualizarse, y el SMAA si cambian la calidad
      acumulado.reiniciar();
      while (!acumulado.listo) {
        acumulado.acumular(renderer, MUESTRAS_POR_TANDA);
        if (!acumulado.listo) await ceder();
      }
      pipe.componer(); // GTAO + OutputPass sobre el promedio; el llamador toma la foto YA
    },
    salir: () => {
      if (fuera) return;
      fuera = true;
      composer.removePass(acumulado);
      acumulado.dispose();
      apagados.forEach((p, i) => { p.enabled = antes[i]; });
      for (const o of ocultos) o.visible = true;
      camera.position.copy(camaraAntes.pos);
      pipe.controls.target.copy(camaraAntes.target);
      pipe.aplicarCalidad(useCalidad.getState().calidad);
      pipe.modoGrabacion(null);
    },
  };
}
