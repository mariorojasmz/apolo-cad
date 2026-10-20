import { useEffect, useRef, type MutableRefObject } from "react";
import { useStore } from "../../state/store";
import type { FeatureOut, JointOut } from "../../types";
import type { VistaCtx } from "../interaccion/ctx";
import { applyKinematicPoses } from "../poses";
import { useMarcha } from "./estado";
import { crearReproductor, type Reproductor } from "./reproductor";

/* El reproductor de la marcha dentro del viewport (plan visor-realista, D4). `Viewport.tsx` lo
   llama DESPUÉS de sus efectos de mallas y pose cinemática (los efectos corren en orden): así el
   reproductor se arma sobre las mallas ya reconstruidas. El bucle de render llama
   `reproRef.current?.tick` en cada fotograma (`pipeline.antesDeComponer`). */

export function useMarchaEnVista(
  ctxRef: MutableRefObject<VistaCtx | null>,
  reproRef: MutableRefObject<Reproductor | null>,
  features: FeatureOut[],
  kinJoints: JointOut[] | null,
  jointValues: Record<string, number>,
  projectId: number | null,
): void {
  const serie = useMarcha((s) => s.serie);
  const token = useMarcha((s) => s.token);
  const tokenRef = useRef(token);
  const gravedad = useStore((s) => s.gravityResult);
  const caida = useStore((s) => s.physicsResult);

  // (re)arma el reproductor: otra serie, o las mallas cambiaron (sigue en el mismo instante)
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    const previo = reproRef.current;
    const t0 = tokenRef.current === token ? previo?.tiempo() ?? 0 : 0;
    tokenRef.current = token;
    previo?.restaurar();
    reproRef.current = null;
    if (!serie) {
      if (previo) applyKinematicPoses(ctx.meshes, kinJoints, jointValues);
      return;
    }
    const m = useMarcha.getState();
    reproRef.current = crearReproductor(serie, ctx.meshes, ctx.scene, () => useMarcha.getState(), {
      saltoHecho: m.saltoHecho,
      publicar: m.publicar,
      alPosar: () => ctx.sombra.marcarSucia(),
    }, t0);
  }, [serie, token, features, kinJoints, jointValues]);

  // la caída por gravedad y el drop-test mueven las mismas mallas: no conviven con la marcha
  useEffect(() => {
    if (gravedad || caida) useMarcha.getState().quitar();
  }, [gravedad, caida]);

  // otro proyecto: la marcha era de la máquina anterior
  useEffect(() => {
    useMarcha.getState().quitar();
  }, [projectId]);

  // al desmontar el viewport, las mallas vuelven a su pose base
  useEffect(() => () => {
    reproRef.current?.restaurar();
    reproRef.current = null;
  }, []);
}
