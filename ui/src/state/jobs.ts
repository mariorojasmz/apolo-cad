import { detalleDeError } from "../api";

/* Los jobs que encola la PERSONA desde el visor (plan visor-para-evaluar D9): correr una prueba,
   calcular la lámina de «Planos», el juego de planos. Se piden con `origen=visor` (el visor no
   los cuenta como «el agente está trabajando», `state/eventosWs.ts`) y se esperan aquí, con el
   long-poll de `GET /api/jobs/{id}`, leyendo su `progreso` entre vuelta y vuelta. */

export interface ProgresoJob {
  hechas: number;
  total: number;
  /** Qué está haciendo: la vista del HLR («alzado»), «corte», «laminas», «listo». */
  fase: string;
}

export interface EstadoJobVisor {
  estado: "encolado" | "corriendo" | "ok" | "error";
  progreso?: ProgresoJob;
  resultado?: Record<string, unknown> | null;
  error?: string | null;
}

/** Un job leído de la API, o un error con el texto del servidor (404 tras un reinicio, etc.). */
export async function leerJob(id: string, esperaS: number): Promise<EstadoJobVisor> {
  const r = await fetch(`/api/jobs/${encodeURIComponent(id)}?wait_s=${esperaS}`);
  if (!r.ok) throw new Error((await detalleDeError(r)) ?? r.statusText);
  return (await r.json()) as EstadoJobVisor;
}

/** Espera a que el job termine: llama `alAvanzar` con cada estado leído (cada ~`esperaS`), da su
   resultado o lanza con el error del job. `cancelado()` corta la espera (el panel se cerró). */
export async function esperarJob(
  id: string, alAvanzar: (e: EstadoJobVisor) => void, cancelado: () => boolean = () => false, esperaS = 2,
): Promise<Record<string, unknown>> {
  for (;;) {
    const e = await leerJob(id, esperaS);
    if (cancelado()) throw new DOMException("cancelado", "AbortError");
    alAvanzar(e);
    if (e.estado === "ok") return e.resultado ?? {};
    if (e.estado === "error") throw new Error(e.error || "El trabajo no terminó bien.");
  }
}

/** El job_id de una respuesta 202 (`{job_id}`) o un error con el texto del servidor. */
export async function encolar(url: string, init?: RequestInit): Promise<string> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error((await detalleDeError(r)) ?? r.statusText);
  const cuerpo = (await r.json()) as { job_id?: unknown };
  if (typeof cuerpo.job_id !== "string") throw new Error("La respuesta no trajo el trabajo encolado.");
  return cuerpo.job_id;
}
