import type { VistaCtx } from "../viewport/interaccion/ctx";
import { crearReproductor, type AvisosReproductor, type Reproductor } from "../viewport/marcha/reproductor";
import type { SerieMarcha } from "../viewport/marcha/serie";
import { useVivo } from "./estado";
import { crearEtiquetas } from "./etiquetas";
import { lecturasDe } from "./lecturas";
import { instalarMandos3D } from "./mandos3d";
import { estadoDeMando } from "./accionar";
import { avanzarReloj, crearReloj } from "./reloj";
import { accionar, sesionViva } from "./sesion";
import { useStore } from "../state/store";

/** La pieza (o una del MISMO comando: el vástago o el empujador de un cilindro) está
 *  seleccionada en el 3D. */
function piezaElegida(pieza: string): boolean {
  const st = useStore.getState();
  if (!st.selection.length) return false;
  if (st.selection.includes(pieza)) return true;
  const feats = st.scene?.features ?? [];
  const cid = feats.find((f) => f.id === pieza)?.command_id;
  if (!cid) return false;
  const sel = new Set(st.selection);
  return feats.some((f) => f.command_id === cid && sel.has(f.id));
}

/* El reproductor de la marcha en modo vivo (plan V8.4, F2): el MISMO de «Ver la marcha»
   (`viewport/marcha/reproductor.ts`) siguiendo el reloj de la sesión viva (`reloj.ts`) sobre una
   serie que crece, más lo que sólo tiene la máquina viva: las etiquetas de datos sobre las
   piezas (D5), el clic en los mandos con pieza y los pilotos con pieza (D4). Lo arma
   `marcha/enVista.ts` cuando la serie cargada es viva; así `Viewport.tsx` no cambia. */

export function crearReproductorVivo(serie: SerieMarcha, ctx: VistaCtx, avisos: AvisosReproductor): Reproductor {
  const reloj = crearReloj();
  const base = crearReproductor(serie, ctx.meshes, ctx.scene, () => ({ reproduciendo: false, velocidad: 1, salto: null }),
    avisos, 0, ctx.group, (nowMs) => avanzarReloj(reloj, nowMs, sesionViva.tUltimo(), sesionViva.factor()));
  const ini = sesionViva.inicio();
  const contenedor = ctx.renderer.domElement.parentElement;
  if (!ini || !contenedor) return base;
  const etiquetas = crearEtiquetas(contenedor, ctx.meshes, lecturasDe(ini, ini.senales), sesionViva.valor,
    (l) => !!l.pieza && piezaElegida(l.pieza));
  const mandos3d = instalarMandos3D({
    contenedor,
    canvas: ctx.renderer.domElement,
    camara: () => ctx.camera,
    meshes: ctx.meshes,
    mandos: ini.mandos,
    pilotos: ini.pilotos,
    valor: sesionViva.valor,
    estado: (m) => estadoDeMando(m, useVivo.getState()),
    enviar: accionar,
  });
  return {
    tiempo: base.tiempo,
    tick: (nowMs) => {
      base.tick(nowMs);
      etiquetas.tick(nowMs, ctx.camera);
      mandos3d.tick(nowMs);
    },
    restaurar: () => {
      mandos3d.quitar();
      etiquetas.quitar();
      base.restaurar();
    },
  };
}
