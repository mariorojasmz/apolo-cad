import { avisoJob, EVENTO_JOB, EVENTO_WS_RECONECTADO, type AvisoJob } from "../state/eventosWs";
import { useVisor } from "./estado";

/* «El agente está trabajando…» en vivo (plan modo-visor, D10). `connectWs` publica en `window`
   cada aviso de job del servidor (`state/eventosWs.ts`); aquí se lleva el conjunto de jobs
   corriendo y `useVisor().trabajando` es «hay alguno». Se instala UNA vez al arrancar
   (main.tsx), como `escucharCambiosExternos`.
   Todo job es del agente: la UI no encola jobs propios (sus lotes y ediciones van sin `?async`,
   que es lo único que crea un job); los encolan el MCP y el chat de la app, que usa las mismas
   tools. Si la UI llegara a encolar uno, habría que filtrarlo aquí por su `job_id`. */

/** Un job que lleva más que esto «corriendo» se da por perdido: red de seguridad por si su
   aviso de fin no llegó (el servidor reinició, el aviso se cayó). */
export const JOB_COLGADO_MS = 10 * 60 * 1000;

/** job_id → cuándo empezó a correr (ms, `Date.now()`). */
export type JobsCorriendo = ReadonlyMap<string, number>;

/** Aplica un aviso: `corriendo` agrega el job (si ya estaba, conserva su inicio); `ok` y
   `error` lo quitan (un fin sin inicio conocido no hace nada). Devuelve un mapa nuevo. */
export function aplicarJob(jobs: JobsCorriendo, a: AvisoJob, ahora: number): Map<string, number> {
  const nuevos = new Map(jobs);
  if (a.estado === "corriendo") {
    if (!nuevos.has(a.job_id)) nuevos.set(a.job_id, ahora);
  } else {
    nuevos.delete(a.job_id);
  }
  return nuevos;
}

/** Quita los jobs que llevan `JOB_COLGADO_MS` o más corriendo. */
export function podarColgados(jobs: JobsCorriendo, ahora: number, maxMs = JOB_COLGADO_MS): Map<string, number> {
  const vivos = new Map<string, number>();
  for (const [id, desde] of jobs) if (ahora - desde < maxMs) vivos.set(id, desde);
  return vivos;
}

/** Cuándo vence el job más viejo (ms), o null si no hay ninguno. */
export function proximoVencimiento(jobs: JobsCorriendo, maxMs = JOB_COLGADO_MS): number | null {
  let min: number | null = null;
  for (const desde of jobs.values()) if (min === null || desde < min) min = desde;
  return min === null ? null : min + maxMs;
}

/** Escucha los avisos de jobs y la reconexión del WS en `origen`; devuelve cómo dejar de
   escuchar. Una reconexión vacía el conjunto: los avisos perdidos dejarían un «trabajando»
   colgado. Un temporizador poda el job colgado aunque no llegue ningún aviso más.
   Al EMPEZAR a trabajar se descarta el aviso de cambios viejo: si no, reaparecería entre el
   fin del job y el refresco que trae el aviso nuevo, contando cambios del lote anterior. */
export function escucharJobs(origen: EventTarget = window): () => void {
  let jobs: JobsCorriendo = new Map();
  let vence: ReturnType<typeof setTimeout> | null = null;

  const fijar = (nuevos: JobsCorriendo) => {
    jobs = nuevos;
    if (vence !== null) clearTimeout(vence);
    vence = null;
    const cuando = proximoVencimiento(jobs);
    if (cuando !== null) vence = setTimeout(() => fijar(podarColgados(jobs, Date.now())), Math.max(0, cuando - Date.now()));

    const visor = useVisor.getState();
    const trabajando = jobs.size > 0;
    if (trabajando === visor.trabajando) return;
    if (trabajando) visor.descartarAviso();
    visor.setTrabajando(trabajando);
  };

  const alJob = (ev: Event) => {
    // el detalle ya viene validado por `publicarJob`; se revalida por si otro lo despacha
    const d = (ev as CustomEvent<unknown>).detail;
    const a = avisoJob(typeof d === "object" && d !== null ? { ...d, type: "job" } : null);
    if (!a) return;
    const ahora = Date.now();
    fijar(aplicarJob(podarColgados(jobs, ahora), a, ahora));
  };
  const alReconectar = () => fijar(new Map());

  origen.addEventListener(EVENTO_JOB, alJob);
  origen.addEventListener(EVENTO_WS_RECONECTADO, alReconectar);
  return () => {
    origen.removeEventListener(EVENTO_JOB, alJob);
    origen.removeEventListener(EVENTO_WS_RECONECTADO, alReconectar);
    if (vence !== null) clearTimeout(vence);
    vence = null;
  };
}
