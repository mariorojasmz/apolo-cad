import * as THREE from "three";
import { useStore } from "../../state/store";
import type { Pipeline } from "../pipeline";
import type { SombraContacto } from "../sombraContacto";
import type { Reproductor } from "../marcha/reproductor";
import type { SerieMarcha } from "../marcha/serie";
import { useMarcha } from "../marcha/estado";
import { crearCaptura } from "./captura";
import { distanciasPorAngulo, puntosDeMallas } from "./encuadre";
import { nombreGpu, sinGpu, type InformeGrabacion } from "./enVista";
import {
  grabarEnSesion, imagenDeSesion, planDeSesion, subirFoto, type AperturaGrabacion,
} from "./grabador";
import { entrarModoGrabacion, MUESTRAS_RAPIDO } from "./modo";
import { crearMontaje } from "./montaje";
import {
  aparicionesPorCuadro, direccion, PARTES_3D, tiempoMarcha, tramoDe, validarPlan, type MarchaPlan,
  type Parte, type PlanGuion,
} from "./planGuion";

/* El video del guion grabado en el visor (plan video-realista, F3 · D5): el MISMO guion que el
   video de VTK —portada, etapas de montaje con sus rótulos, la máquina andando, cifras, la vuelta
   final y el cierre—, con el plan cuadro por cuadro que arma la API. Lo usan el botón «Grabar
   video» y el modo sin ventana de `publicar generar --render navegador` (`?grabar=<sesion>`).

   Orden: el plan → la escena cargada → la serie de la marcha y los rótulos → la foto de la
   máquina terminada (portada y miniatura) → las tarjetas → los cuadros. Al terminar, bien o mal,
   el visor vuelve a como estaba (mallas, materiales, cámara, calidad y la marcha que había). */

export interface DepsGuion {
  pipe: Pipeline;
  sombra: SombraContacto;
  /** El reproductor de la marcha que arma el visor (null sin marcha). */
  marcha: () => Reproductor | null;
  /** Lo que el visor tiene encima y no sale en un video (tiradores, medida). */
  ocultar: () => THREE.Object3D[];
}

export interface OpcionesSesion {
  muestras?: number;
  permitirSinGpu?: boolean;
  /** Si algo falla, borrar la sesión (el botón); la del CLI la borra el CLI (false). */
  descartar?: boolean;
  cancelado?: () => boolean;
  progreso?: (avance: { dibujados: number; subidos: number; total: number }) => void;
}

/** El navegador dibuja sin GPU: `publicar generar` cae al respaldo VTK. */
export class SinGpu extends Error {}

export type GrabarSesion = (sesion: string | AperturaGrabacion, op?: OpcionesSesion) => Promise<InformeGrabacion>;

const dormir = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function esperar(cond: () => boolean, ms: number, error: string): Promise<void> {
  const t0 = performance.now();
  while (!cond()) {
    if (performance.now() - t0 > ms) throw new Error(error);
    await dormir(50);
  }
}

/** La escena del proyecto del plan cargada en el visor, con sus mallas ya armadas. */
async function esperarEscena(plan: PlanGuion, mallas: Map<string, THREE.Mesh>): Promise<void> {
  await esperar(() => {
    const s = useStore.getState().scene;
    return !!s && (plan.proyecto == null || s.document.project_id === plan.proyecto) && mallas.size > 0;
  }, 180_000, "El visor no terminó de cargar la máquina: vuelve a intentarlo.");
  for (let n = -1; n !== mallas.size;) { // las mallas dejan de crecer
    n = mallas.size;
    await dormir(400);
  }
}

async function traerSerie(m: MarchaPlan): Promise<SerieMarcha> {
  const r = await fetch("/api/physics/dynamics/serie", m.escenario
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(m.escenario) }
    : undefined);
  const s = (await r.json().catch(() => ({}))) as SerieMarcha & { detail?: string };
  if (!r.ok) throw new Error(s.detail ?? `La marcha no se pudo simular (${r.status}).`);
  if (!s.t || s.t.length < 2) throw new Error(s.mensaje ?? "La simulación no tiene movimiento que mostrar.");
  return s;
}

/** Quita la marcha del visor y espera a que sus mallas vuelvan a su pose. */
async function quitarMarcha(d: DepsGuion): Promise<void> {
  useMarcha.getState().quitar();
  await esperar(() => !d.marcha(), 5_000, "La marcha anterior no se pudo quitar del visor.");
}

/** Pone la serie en el visor, quieta (la mueve el reloj del video con `saltar`). */
async function cargarMarcha(d: DepsGuion, serie: SerieMarcha): Promise<void> {
  useMarcha.getState().cargar(serie);
  useMarcha.setState({ reproduciendo: false });
  await esperar(() => !!d.marcha(), 10_000, "La máquina andando no se pudo armar en el visor.");
}

async function tarjetas(sesion: string, plan: PlanGuion): Promise<Map<Parte, ImageBitmap>> {
  const partes = [...new Set(plan.tramos.map((t) => t.parte).filter((p) => !PARTES_3D.has(p)))];
  const imagenes = await Promise.all(partes.map((p) => imagenDeSesion(sesion, `tarjeta/${p}`)));
  return new Map(partes.map((p, i) => [p, imagenes[i]]));
}

export function crearGrabacionGuion(d: DepsGuion): GrabarSesion {
  let grabando = false;
  return async (apertura, op = {}) => {
    if (grabando) throw new Error("Ya hay una grabación en curso: espera a que termine.");
    const gpu = nombreGpu(d.pipe.renderer);
    if (sinGpu(gpu) && !op.permitirSinGpu) {
      throw new SinGpu(`Este navegador dibuja sin GPU (${gpu}) y el video tardaría horas.`);
    }
    grabando = true;
    const sesion = typeof apertura === "string" ? apertura : apertura.sesion;
    try {
      const plan = validarPlan(await planDeSesion(sesion));
      await esperarEscena(plan, d.pipe.meshes);
      const [serie, rotulos] = await Promise.all([
        plan.marcha ? traerSerie(plan.marcha) : Promise.resolve(null),
        Promise.all(plan.etapas.map((_, i) => imagenDeSesion(sesion, `rotulo/${i}`))),
      ]);
      const store = useStore.getState();
      store.clearGravity(); // mueven las mismas mallas que el montaje y la marcha
      store.clearPhysics();
      const antes = useMarcha.getState();
      const previa = antes.serie ? { serie: antes.serie, t: antes.t } : null;
      if (d.marcha()) await quitarMarcha(d);
      const r = await grabarPlan(d, sesion, plan, serie, rotulos, op);
      if (previa) {
        useMarcha.getState().cargar(previa.serie);
        useMarcha.setState({ reproduciendo: false });
        useMarcha.getState().saltar(previa.t);
      }
      return { ...r, gpu, segundosPorCuadro: r.segundosCuadros / plan.cuadros };
    } finally {
      grabando = false;
    }
  };
}

async function grabarPlan(
  d: DepsGuion, sesion: string, plan: PlanGuion, serie: SerieMarcha | null, rotulos: ImageBitmap[],
  op: OpcionesSesion,
) {
  const { ancho, alto, fps } = plan.video;
  const { pipe } = d;
  const camara = pipe.camera;
  const modo = entrarModoGrabacion(pipe, { ancho, alto, muestras: op.muestras ?? MUESTRAS_RAPIDO,
    ocultar: d.ocultar() });
  const montaje = crearMontaje(pipe.meshes, plan.ids);
  try {
    // la máquina TERMINADA encuadra todo el video: lo justo en cada ángulo (`encuadre.ts`)
    const objetivo = montaje.caja().getCenter(new THREE.Vector3());
    const distancia = distanciasPorAngulo(camara, objetivo, puntosDeMallas(montaje.mallas()),
      plan.camara.elevacion);
    pipe.controls.target.copy(objetivo);
    const poner = (az: number) => {
      const [x, y, z] = direccion(az, plan.camara.elevacion);
      const d = distancia(az);
      camara.position.set(objetivo.x + x * d, objetivo.y + y * d, objetivo.z + z * d);
      camara.lookAt(objetivo);
    };
    // la máquina terminada: el fondo de la portada y de la miniatura
    poner(plan.camara.azimut_inicial);
    d.sombra.marcarSucia();
    await modo.cuadro(0);
    await subirFoto(sesion, await crearCaptura(ancho, alto, "png").tomar(pipe.renderer.domElement).foto);
    const fijas = await tarjetas(sesion, plan);
    montaje.vaciar();
    d.sombra.marcarSucia();
    const captura = crearCaptura(ancho, alto, "jpeg");
    const entran = aparicionesPorCuadro(plan);
    let completa = false;
    return await grabarEnSesion({ sesion } as AperturaGrabacion, {
      fps, cuadros: plan.cuadros, cancelado: op.cancelado, progreso: op.progreso,
      dibujar: async (n, ms) => {
        const t = tramoDe(plan, n);
        let origen: CanvasImageSource;
        if (PARTES_3D.has(t.parte)) {
          if (t.parte !== "etapa" && !completa) { // la máquina terminada, con lo que no tenía tanda
            montaje.completar();
            completa = true;
            d.sombra.marcarSucia();
          }
          if (t.parte === "marcha" && serie && !d.marcha()) await cargarMarcha(d, serie);
          const nuevos = entran.get(n);
          if (nuevos) {
            montaje.sumar(nuevos, n);
            d.sombra.marcarSucia();
          }
          montaje.resaltar(n, fps, plan.resalte_s);
          const tm = serie ? tiempoMarcha(plan, n, serie.duracion_s) : null;
          if (tm !== null && d.marcha()) useMarcha.getState().saltar(tm); // lo consume el reproductor
          poner(plan.cuadro.az[n] ?? plan.camara.azimut_inicial);
          await modo.cuadro(ms);
          origen = pipe.renderer.domElement;
        } else {
          origen = fijas.get(t.parte)!;
        }
        return captura.tomar(origen, {
          rotulo: t.parte === "etapa" && t.etapa !== null
            ? { imagen: rotulos[t.etapa], opacidad: plan.cuadro.rotulo[n] } : null,
          empiezaCruce: t.cruza && n === t.inicio,
          mezcla: plan.cuadro.mezcla[n],
          luz: plan.cuadro.luz[n],
        });
      },
    }, { descartar: op.descartar });
  } finally {
    if (d.marcha()) await quitarMarcha(d).catch(() => undefined);
    montaje.restaurar();
    modo.salir();
    d.sombra.marcarSucia();
  }
}
