/* El plan del video cuadro por cuadro que arma la API desde el guion (plan video-realista, D5;
   `core/apolo/publicacion/plan_navegador.py`). La API calcula TODO lo que decide el guion —qué
   parte va en cada cuadro, qué piezas entran, la órbita, los fundidos y la opacidad del rótulo—
   con las mismas funciones que el video de VTK; aquí sólo se lee. Puro: sin three ni DOM. */

export type Parte = "portada" | "etapa" | "marcha" | "cifras" | "orbita" | "cierre";

export interface TramoPlan {
  parte: Parte;
  inicio: number;
  /** Primer cuadro que ya NO es de la parte. */
  fin: number;
  etapa: number | null;
  /** Entra con fundido cruzado desde el último cuadro de la parte anterior. */
  cruza: boolean;
}

export interface MarchaPlan {
  inicio: number;
  fin: number;
  duracion_s: number;
  /** La petición de la simulación; null = la última marcha simulada del proyecto. */
  escenario: Record<string, unknown> | null;
}

export interface PlanGuion {
  version: number;
  titulo: string;
  video: { ancho: number; alto: number; fps: number };
  cuadros: number;
  tramos: TramoPlan[];
  etapas: { titulo: string; texto: string }[];
  /** Las piezas visibles de la máquina terminada. */
  ids: string[];
  /** Las piezas que entran en cada cuadro de las etapas (en orden de cuadro). */
  apariciones: { cuadro: number; ids: string[] }[];
  marcha: MarchaPlan | null;
  camara: { elevacion: number; azimut_inicial: number };
  resalte_s: number;
  proyecto: number | null;
  cuadro: {
    az: (number | null)[];
    luz: number[];
    mezcla: (number | null)[];
    rotulo: number[];
    marcha_t: (number | null)[];
  };
}

/** Las partes que se dibujan en 3D; las demás son tarjetas que manda la API. */
export const PARTES_3D: ReadonlySet<Parte> = new Set(["etapa", "marcha", "orbita"]);

/** Revisa lo mínimo para no grabar 2 000 cuadros con un plan roto. */
export function validarPlan(x: unknown): PlanGuion {
  const p = x as PlanGuion;
  const n = p?.cuadros;
  const ok = !!p && p.version === 1 && Number.isInteger(n) && n > 0 && Array.isArray(p.tramos)
    && p.tramos.length > 0 && p.tramos[p.tramos.length - 1].fin === n
    && (["az", "luz", "mezcla", "rotulo", "marcha_t"] as const).every((k) => p.cuadro?.[k]?.length === n);
  if (!ok) throw new Error("El plan del video llegó incompleto: vuelve a abrir la grabación.");
  return p;
}

/** La parte del cuadro `n` (los tramos van en orden y sin huecos). */
export function tramoDe(plan: PlanGuion, n: number): TramoPlan {
  let a = 0;
  let b = plan.tramos.length - 1;
  while (a < b) {
    const m = (a + b) >> 1;
    if (plan.tramos[m].fin <= n) a = m + 1;
    else b = m;
  }
  return plan.tramos[a];
}

/** Dirección de la cámara desde el centro de la máquina: azimut alrededor de Z y elevación
   sobre el plano XY, en grados (la convención de `render_view` y del video de VTK). */
export function direccion(azimut: number, elevacion: number): [number, number, number] {
  const a = (azimut * Math.PI) / 180;
  const e = (elevacion * Math.PI) / 180;
  return [Math.cos(e) * Math.cos(a), Math.cos(e) * Math.sin(a), Math.sin(e)];
}

/** {cuadro → piezas que entran ahí}. */
export function aparicionesPorCuadro(plan: PlanGuion): Map<number, string[]> {
  return new Map(plan.apariciones.map((a) => [a.cuadro, a.ids]));
}

/** El resaltado de lo que entró en el cuadro `n0`, visto en el cuadro `n`: de 1 a 0 en
   `resalte_s` (= `linea_tiempo.resalte`). */
export function intensidadResalte(n: number, n0: number, fps: number, resalteS: number): number {
  const x = 1 - (n - n0) / Math.max(1, resalteS * fps);
  return Math.min(Math.max(x, 0), 1);
}

/** El tiempo de la marcha en el cuadro `n` (s), sin pasarse del final de la serie; null si en
   ese cuadro la máquina no anda. */
export function tiempoMarcha(plan: PlanGuion, n: number, duracionSerie: number): number | null {
  const t = plan.cuadro.marcha_t[n];
  return t === null || t === undefined ? null : Math.min(Math.max(t, 0), duracionSerie);
}
