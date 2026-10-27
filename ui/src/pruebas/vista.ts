import { cifra } from "../diseno/cifra";
import type { Incidencia } from "./tipos";

/* Lo que el panel «Pruebas» dice con los datos de la API (plan visor-para-evaluar D3–D5). Puro:
   lo prueban los tests y lo usan el panel y el muestrario. */

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/** «hoy, 14:03», «ayer, 09:10» o «26 oct, 14:03» (con el año si no es el de `ahora`). */
export function fechaCorta(iso: string | undefined, ahora: Date = new Date()): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  if (!m) return "";
  const [, a, mes, dia, h, min] = m;
  const f = new Date(Number(a), Number(mes) - 1, Number(dia));
  const hoy = new Date(ahora.getFullYear(), ahora.getMonth(), ahora.getDate());
  const dias = Math.round((hoy.getTime() - f.getTime()) / 86_400_000);
  const hora = `${h}:${min}`;
  if (dias === 0) return `hoy, ${hora}`;
  if (dias === 1) return `ayer, ${hora}`;
  const fecha = `${Number(dia)} ${MESES[Number(mes) - 1]}${Number(a) !== ahora.getFullYear() ? ` ${a}` : ""}`;
  return `${fecha}, ${hora}`;
}

/** «12 s», «1 min 40 s», «4 min». */
export function duracion(s: number): string {
  const t = Math.max(0, Math.round(s));
  if (t < 60) return `${t} s`;
  const min = Math.floor(t / 60), seg = t % 60;
  return seg && min < 10 ? `${min} min ${seg} s` : `${min} min`;
}

export interface Corrida {
  jobId: string;
  estado: "encolado" | "corriendo";
  /** Cuándo empezó a CORRER (ms del reloj de la página); null mientras espera en la cola. */
  desde: number | null;
  estimadoS?: number;
}

/** La frase y la fracción (0…1, o null si no hay con qué estimarla) del progreso de una corrida:
   el worker de la co-simulación no publica avance, así que se estima con lo que tardó la última
   vez (nunca llega a 1 sola: lo cierra el fin del job). */
export function progresoCorrida(c: Corrida, ahora: number): { frase: string; fraccion: number | null } {
  if (c.estado === "encolado" || c.desde === null) return { frase: "En espera: otra prueba está corriendo", fraccion: null };
  const lleva = (ahora - c.desde) / 1000;
  if (!c.estimadoS) return { frase: `Corriendo · ${duracion(lleva)}`, fraccion: null };
  const fraccion = Math.min(0.95, lleva / c.estimadoS);
  return { frase: `Corriendo · ${duracion(lleva)} de unos ${duracion(c.estimadoS)}`, fraccion };
}

/** «Caja 3 trabada cerca de «Banda» a los 12,4 s» (o con la coordenada si no hay pieza cerca). */
export function textoIncidencia(i: Incidencia): string {
  if (i.mas) return `y ${i.mas} más`;
  const que = i.que ?? i.tipo;
  const donde = i.cerca_de
    ? ` cerca de «${i.cerca_de}»`
    : i.punto_mm ? ` en (${i.punto_mm.map((c) => cifra(c)).join("; ")}) mm` : "";
  const cuando = i.hora_s !== undefined ? ` a los ${cifra(i.hora_s, i.hora_s < 10 ? 1 : 0)} s` : "";
  return `${i.producto ?? "Producto"} ${que}${donde}${cuando}`;
}
