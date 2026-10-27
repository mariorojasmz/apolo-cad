import type { Severidad } from "../diseno/atencion";
import { designacionSecundaria, nombreEnFrase, nombrePrincipal } from "../diseno/nombres";
import { abreYCierra } from "./accionar";
import type { InicioVivo, MandoVivo } from "./protocolo";

/* Cómo se LEE el panel «Mandos» (plan nombres-por-funcion D9–D12): el nombre de cada fila, los
   grupos, los segmentos de un mando que se queda, el estado de un rearme y el veredicto de arriba.
   Los nombres los da el servidor (`rotulo`, `estados`, `grupo`, `rearma` del `inicio`): aquí no
   hay tabla de tipos. Sin rótulo (un servidor anterior), lo principal es la designación. Los
   estados se LEEN de las señales, nunca de lo último que se tocó. Puro (se prueba en node). */

/** Las señales leídas: los números (`lecturas`) y los textos (`textos`). */
export interface Leidas {
  valor: (senal: string) => number | undefined;
  texto: (senal: string) => string | undefined;
}

// lo principal y lo secundario del nombre son de todas las superficies (`diseno/nombres.ts`)
export { designacionSecundaria, nombrePrincipal };

// ── grupos (D11) ─────────────────────────────────────────────────────────────────────────────

/** Con más de estos mandos se agrupan por propósito. */
export const MAX_SIN_GRUPOS = 5;
const GRUPOS: readonly { clave: string; titulo: string }[] = [
  { clave: "energia", titulo: "Energía" },
  { clave: "seguridad", titulo: "Seguridad" },
  { clave: "operacion", titulo: "Operación" },
];

export interface GrupoMandos {
  clave: string;
  titulo: string;
  mandos: MandoVivo[];
}

/** Los mandos en grupos: Energía, Seguridad y Operación con más de 5 y el `grupo` del servidor;
 *  si no, un solo grupo «Mandos». Lo que no trae grupo conocido va a Operación. */
export function gruposDeMandos(mandos: readonly MandoVivo[]): GrupoMandos[] {
  if (mandos.length <= MAX_SIN_GRUPOS || !mandos.some((m) => m.grupo)) {
    return [{ clave: "mandos", titulo: "Mandos", mandos: [...mandos] }];
  }
  const de = (m: MandoVivo) => (GRUPOS.some((g) => g.clave === m.grupo) ? m.grupo : "operacion");
  return GRUPOS.map((g) => ({ ...g, mandos: mandos.filter((m) => de(m) === g.clave) })).filter((g) => g.mandos.length);
}

// ── el control segmentado (D9) ───────────────────────────────────────────────────────────────

export interface Segmento {
  clave: string;
  rotulo: string;
}

/** Los segmentos de un mando que SE QUEDA: el selector, sus posiciones (con su nombre si lo
 *  tiene); el seccionador y el resguardo, «cerrado» y «abierto» con sus nombres, en el orden del
 *  servidor. null: es un botón (pulsador, seta) o un servidor anterior sin `estados`. */
export function segmentosDe(m: MandoVivo): Segmento[] | null {
  if (m.tipo === "selector") {
    const pos = m.posiciones ?? [];
    return pos.length ? pos.map((p) => ({ clave: p, rotulo: m.estados?.[p] || p })) : null;
  }
  if (!abreYCierra(m) || !m.estados?.cerrado || !m.estados?.abierto) return null;
  return Object.entries(m.estados).filter(([k]) => k === "cerrado" || k === "abierto").map(([clave, rotulo]) => ({ clave, rotulo }));
}

/** El segmento que dicen las señales: la posición del selector (`<des>.posicion`, texto) o
 *  «cerrado»/«abierto» (`<des>.cerrado`). undefined sin señal todavía: ninguno marcado. */
export function segmentoLeido(m: MandoVivo, leidas: Leidas): string | undefined {
  if (m.tipo === "selector") return leidas.texto(`${m.designacion}.posicion`);
  if (!abreYCierra(m)) return undefined;
  const v = leidas.valor(`${m.designacion}.cerrado`);
  return v === undefined ? undefined : v >= 0.5 ? "cerrado" : "abierto";
}

// ── el estado al lado del botón (D10) ────────────────────────────────────────────────────────

/** Lo que dice la fila de un botón junto al verbo: la seta, si está presionada; el rearme, el
 *  estado de los relés que rearma («Falta rearmar» / «Rearmada»). null si no se sabe todavía o el
 *  mando no tiene nada que decir (un pulsador común). */
export function estadoJuntoAlBoton(m: MandoVivo, leidas: Leidas): string | null {
  if (m.tipo === "seta") {
    const v = leidas.valor(`${m.designacion}.accionado`);
    return v === undefined ? null : v >= 0.5 ? "Presionada" : "Liberada";
  }
  const reles = m.rearma ?? [];
  if (!reles.length) return null;
  const salidas = reles.map((k) => leidas.valor(`${k}.salidas`));
  if (salidas.some((v) => v === undefined)) return null;
  return salidas.every((v) => v! >= 0.5) ? "Rearmada" : "Falta rearmar";
}

// ── el veredicto (D12) ───────────────────────────────────────────────────────────────────────

/** El mando que el veredicto pide tocar: su botón o, si se queda, el segmento a elegir (`clave`). */
export interface PasoSiguiente {
  designacion: string;
  clave?: string;
}

export interface VeredictoMandos {
  severidad: Severidad;
  /** La causa, leída de las señales: «Tapa del tanque abierta». */
  frase: string;
  /** La acción siguiente, de los mismos hechos: «Cierra la tapa del tanque». */
  nota?: string;
  /** El control de esa acción: va destacado (estilo primario) en su fila. */
  paso?: PasoSiguiente;
}

/** «Tapa del tanque abierta»: el rótulo con el nombre de su estado (la concordancia la declara el
 *  modelador en `estados`); un estado de varias palabras va tras dos puntos. */
function conEstado(m: MandoVivo, clave: string, porDefecto: string): string {
  const est = (m.estados?.[clave] || porDefecto).toLowerCase();
  return `${nombrePrincipal(m)}${est.includes(" ") ? ":" : ""} ${est}`;
}

/** Cerrar un resguardo dicho con SU estado: «Cierra la tapa del tanque»; con un estado que no es
 *  «cerrado» («Acoplado»), «Pon el recipiente bajo la descarga en «Acoplado»». */
function accionCerrar(m: MandoVivo): string {
  const est = m.estados?.cerrado || "Cerrado";
  return /^cerrad[oa]s?$/i.test(est) ? `Cierra ${nombreEnFrase(m)}` : `Pon ${nombreEnFrase(m)} en «${est}»`;
}

interface Hecho extends Omit<VeredictoMandos, "severidad"> { nota: string }

/** Lo que bloquea la marcha, SÓLO con hechos leídos de las señales y en orden de bloqueo: sin
 *  energía, parada de emergencia presionada, resguardo abierto, seguridad sin rearmar. La frase es
 *  la causa del primero y la nota, su acción («Libera la parada de emergencia»); `paso`, el control
 *  que la hace. Un relé nunca se nombra con un verbo pegado. Sin nada de eso, «Energía y seguridad
 *  habilitadas»: nunca «lista para arrancar» (el permiso del PLC no se conoce). null si no hay nada
 *  que leer (sin esos aparatos o sin señales todavía). */
export function veredictoMandos(ini: Pick<InicioVivo, "mandos" | "dispositivos">, leidas: Leidas): VeredictoMandos | null {
  const hechos: Hecho[] = [];
  let leido = false;
  const valor = (s: string) => {
    const v = leidas.valor(s);
    if (v !== undefined) leido = true;
    return v;
  };
  const de = (tipo: string) => ini.mandos.filter((m) => m.tipo === tipo);
  for (const m of de("seccionador")) {
    const v = valor(`${m.designacion}.cerrado`);
    if (v !== undefined && v < 0.5 && !hechos.length) {
      hechos.push({ frase: "Sin energía", nota: `Enciende ${nombreEnFrase(m)}`, paso: { designacion: m.designacion, clave: "cerrado" } });
    }
  }
  for (const m of de("seta")) {
    const v = valor(`${m.designacion}.accionado`);
    if (v !== undefined && v >= 0.5) {
      hechos.push({ frase: conEstado(m, "presionada", "presionada"), nota: `Libera ${nombreEnFrase(m)}`,
        paso: { designacion: m.designacion } });
    }
  }
  for (const m of de("resguardo")) {
    const v = valor(`${m.designacion}.cerrado`);
    if (v !== undefined && v < 0.5) {
      hechos.push({ frase: conEstado(m, "abierto", "abierto"), nota: accionCerrar(m),
        paso: { designacion: m.designacion, clave: "cerrado" } });
    }
  }
  // un relé que corta: la seguridad sin rearmar, y el paso es el mando que lo rearma (S34)
  const cortan = ini.dispositivos.filter((d) => d.tipo === "rele_seguridad")
    .filter((k) => { const v = valor(`${k.designacion}.salidas`); return v !== undefined && v < 0.5; })
    .map((k) => k.designacion);
  if (cortan.length) {
    const rearme = ini.mandos.find((m) => m.rearma?.some((k) => cortan.includes(k)));
    hechos.push({ frase: "Seguridad sin rearmar", nota: "Rearma la seguridad",
      ...(rearme ? { paso: { designacion: rearme.designacion } } : {}) });
  }
  if (!leido) return null;
  if (!hechos.length) return { severidad: "bien", frase: "Energía y seguridad habilitadas" };
  return { severidad: "aviso", ...hechos[0] };
}

// ── el color físico (F5b) ────────────────────────────────────────────────────────────────────

/** El cuadrado del color de la tapa sólo donde el color informa: pulsador y seta (los pilotos,
 *  con su lámpara). En el seccionador, el resguardo y el selector parecía una casilla sin marcar. */
export function muestraColorFisico(m: Pick<MandoVivo, "tipo">): boolean {
  return m.tipo === "pulsador" || m.tipo === "seta";
}
