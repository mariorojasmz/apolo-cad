import { cifra } from "../diseno/cifra";
import type { ConNombre } from "../diseno/nombres";
import type { CilindroDetalle, EsquemaNeumatico, NombreNeumatico, PresionLinea, SimboloEsquema, ValvulaEsquema } from "./tipos";

/* La lógica pura del esquema vivo del panel «Neumática» (plan V8.9 D12): la presión de cada línea
   con las señales de la sesión viva, su color en la escala, en qué posición está cada válvula,
   qué aparatos están elegidos por la selección del 3D y cómo se escriben las cifras del detalle.
   Ninguna regla de ingeniería: de qué señal sale cada presión lo decide el servidor. */

/** Lee una señal numérica (bar, 0/1) y una de texto (la posición de una válvula). */
export interface Lector {
  num: (senal: string) => number | undefined;
  texto: (senal: string) => string | undefined;
}

/** La presión manométrica (bar) de una línea, o undefined si no hay señal (o la vía está cerrada). */
export function presionDe(p: PresionLinea | undefined, l: Lector): number | undefined {
  if (!p) return undefined;
  if (p.atmosfera) return 0;
  if (p.senal) {
    const v = l.num(p.senal);
    if (v === undefined || !Number.isFinite(v)) return undefined;
    if (p.si) {
      const abierta = l.num(p.si);
      if (abierta === undefined) return undefined;
      return abierta >= 0.5 ? Math.max(0, v) : 0;
    }
    return Math.max(0, v);
  }
  if (p.valvula && p.tabla) {
    const pos = l.texto(`${p.valvula}.posicion`);
    if (pos === undefined || !(pos in p.tabla)) return undefined;
    const a = p.tabla[pos];
    if (a === "1") return presionDe(p.alimentacion, l);
    if (a === "3" || a === "5") return 0;
    return undefined; // cerrada: queda con lo que tenía, no lo sabemos
  }
  return undefined;
}

/* La escala de la presión (excepción de color por dato, ui/CLAUDE.md): UN tono (azul), del oscuro
   (sin presión) al claro (la regulada), en 5 pasos de la rampa de referencia de la guía de dataviz,
   validada como rampa ordinal contra el fondo de los paneles (#1e222b) y el del visor (#121419) con
   `validate_palette.js --ordinal`: todo PASA (el paso más oscuro, 2,40:1 contra el panel). Siempre
   con su leyenda. */
export const RAMPA_PRESION = ["#1c5cab", "#2a78d6", "#5598e7", "#86b6ef", "#b7d3f6"] as const;
/** Sin presión (bajo `SIN_AIRE_BAR`): un gris NEUTRO, no el primer azul (la revisión a ciegas: el
   azul oscuro casi no se distinguía y se leía como «algo de aire»). 3,3:1 contra `--panel`. */
export const SIN_PRESION = "#6b7280";
export const SIN_AIRE_BAR = 0.1;

/** El paso de la escala de una presión: -2 sin aire, 0 … 4 con aire, -1 sin dato. */
export function pasoDe(bar: number | undefined, escala: number): number {
  if (bar === undefined || !Number.isFinite(bar)) return -1;
  if (bar < SIN_AIRE_BAR) return -2;
  const n = RAMPA_PRESION.length;
  const f = escala > 0 ? bar / escala : 0;
  return Math.min(n - 1, Math.max(0, Math.ceil(f * n) - 1));
}

export function colorPresion(bar: number | undefined, escala: number): string | null {
  const k = pasoDe(bar, escala);
  return k === -1 ? null : k === -2 ? SIN_PRESION : RAMPA_PRESION[k];
}

/** El tope de la leyenda («6 bar»). */
export function topeLeyenda(escala: number): string {
  return cifra(escala, Number.isInteger(escala) ? 0 : 1, "bar");
}

/** En qué posición está una válvula («14», «12», «0»; la de corte, «abierta» o «cerrada»). */
export function posicionDe(v: ValvulaEsquema, l: Lector): string | undefined {
  if (v.tipo === "valvula_corte") {
    const x = l.num(v.senal);
    return x === undefined ? undefined : x >= 0.5 ? "abierta" : "cerrada";
  }
  return l.texto(v.senal);
}

/** Los aparatos cuya pieza (o alguna de las del mismo comando) está seleccionada en el 3D. */
export function elegidosPor(simbolos: readonly SimboloEsquema[], seleccion: readonly string[]): Set<string> {
  const sel = new Set(seleccion);
  return new Set(simbolos.filter((s) => s.piezas.some((p) => sel.has(p))).map((s) => s.designacion));
}

/** Píxeles por mm del esquema: ajustado al ancho del panel (nunca menos de `MIN_PX_MM`) o, a
   pedido, AMPLIADO a lo que se lee cómodo (los textos de la lámina miden 2–3 mm: a 4 px/mm,
   ~10 px) y el esquema se desplaza. */
export const MIN_PX_MM = 1.5;
export const AMPLIADO_PX_MM = 4;
export function escalaEsquema(anchoPx: number, anchoMm: number, ampliado = false): number {
  const ajuste = anchoMm > 0 ? anchoPx / anchoMm : MIN_PX_MM;
  return Math.max(ampliado ? AMPLIADO_PX_MM : MIN_PX_MM, ajuste);
}

/** La vista del esquema [x, y, ancho, alto] (mm) agrandada para que ningún texto se corte en el
 *  borde (F5b: «-RZ2» perdía su «2»): la lámina mide los textos a su alto y aquí crecen hasta
 *  `MIN_TEXTO_PX`. El ancho de un texto se estima en 0,62 × su alto por carácter (cota alta de la
 *  letra del tema); se ajusta dos veces, porque la escala depende del ancho que resulta. */
export function vistaConTextos(vista: readonly number[], textos: EsquemaNeumatico["textos"], anchoPx: number,
  ampliado = false): [number, number, number, number] {
  let out: [number, number, number, number] = [vista[0], vista[1], vista[2], vista[3]];
  for (let vuelta = 0; vuelta < 2; vuelta++) {
    const k = escalaEsquema(anchoPx, out[2], ampliado);
    let [x0, y0] = [vista[0], vista[1]];
    let [x1, y1] = [vista[0] + vista[2], vista[1] + vista[3]];
    for (const t of textos) {
      if (t.clase === "detalle") continue; // los detalles no se dibujan en línea
      const alto = altoTexto(t.alto, k);
      const ancho = t.texto.length * alto * 0.62;
      const ini = t.anclaje === "end" ? t.x - ancho : t.anclaje === "middle" ? t.x - ancho / 2 : t.x;
      x0 = Math.min(x0, ini - 0.5);
      x1 = Math.max(x1, ini + ancho + 0.5);
      y0 = Math.min(y0, t.y - alto);
      y1 = Math.max(y1, t.y + alto * 0.3);
    }
    out = [x0, y0, x1 - x0, y1 - y0];
  }
  return out;
}

/** Si vale la pena ofrecer «Ampliar»: ajustado al ancho se lee chico. */
export function convieneAmpliar(anchoPx: number, anchoMm: number): boolean {
  return anchoMm > 0 && anchoPx / anchoMm < AMPLIADO_PX_MM * 0.9;
}

// ── el detalle ───────────────────────────────────────────────────────────────────────────

/** «Ø32 mm, vástago 12 mm · carrera 200 mm». */
export function rotuloCilindro(c: CilindroDetalle): string {
  const partes: string[] = [];
  if (c.diametro_mm) partes.push(`Ø${cifra(c.diametro_mm, 0, "mm")}${c.vastago_mm ? `, vástago ${cifra(c.vastago_mm, 0, "mm")}` : ""}`);
  if (c.carrera_mm) partes.push(`carrera ${cifra(c.carrera_mm, 0, "mm")}`); // no se parte (F5b)
  return partes.join(" · ");
}

/** Lo que el esquema dice del aparato elegido DETRÁS de su nombre (plan nombres-por-funcion D9):
   qué es y adónde va cada bobina, «Válvula 5/2 monoestable · bobina A1 → +TAB1-S2:14». El nombre
   (lo que hace, del servidor) y la designación los pone `NombreAparato`. */
export function detalleSimbolo(s: Pick<SimboloEsquema, "rotulo" | "bornes">): string {
  const bornes = (s.bornes ?? []).map((b) => {
    const [borne, destino] = b.split(": ");
    return destino ? `bobina ${borne} → ${destino}` : b;
  });
  return [s.rotulo, ...bornes].filter(Boolean).join(" · ");
}

/** El nombre de un aparato de aire con su designación: el rótulo de `nombres` (del servidor) o,
   sin él, la designación sola. */
export function conNombre(designacion: string, nombres?: Record<string, NombreNeumatico>): ConNombre {
  const rotulo = nombres?.[designacion]?.rotulo;
  return rotulo ? { designacion, rotulo } : { designacion };
}

/** Píxeles de letra de un texto del esquema: el de la lámina, nunca menos que `--fs-nota`
   (11 px: la revisión a ciegas leyó 5–6 px). Crece el texto de las designaciones, no el dibujo. */
export const MIN_TEXTO_PX = 11;
export function altoTexto(altoMm: number, pxPorMm: number): number {
  return Math.max(altoMm, pxPorMm > 0 ? MIN_TEXTO_PX / pxPorMm : altoMm);
}

/** [«Avance 483 N (434 N efectivos)», «Retroceso 415 N (373 N efectivos)»]: una línea cada uno. */
export function textoFuerza(f: NonNullable<CilindroDetalle["fuerza"]>): [string, string] {
  return [`Avance ${cifra(f.F_avance_N, 0, "N")} (${cifra(f.F_avance_ef_N, 0, "N")} efectivos)`,
    `Retroceso ${cifra(f.F_retroceso_N, 0, "N")} (${cifra(f.F_retroceso_ef_N, 0, "N")} efectivos)`];
}

/** «2,29 NL por ciclo · 45,9 NL/min a 20 ciclos/min». */
export function textoConsumo(c: NonNullable<CilindroDetalle["consumo"]>): string {
  const base = `${cifra(c.ciclo_NL, 2, "NL")} por ciclo`;
  if (c.NL_min === undefined) return base;
  return `${base} · ${cifra(c.NL_min, 1, "NL/min")}${c.ciclos_min ? ` a ${cifra(c.ciclos_min)} ciclos/min` : ""}`;
}

/** «Avance 0,16 s · retroceso 0,19 s», y de dónde sale. */
export function textoTiempo(t: NonNullable<CilindroDetalle["tiempo"]>): { cifras: string; origen: string } {
  // centésimas (F5b): «0,16 s»; las milésimas eran una precisión que el cálculo no tiene
  const cifras = `Avance ${cifra(t.avance_s, 2, "s")}${t.retroceso_s != null ? ` · retroceso ${cifra(t.retroceso_s, 2, "s")}` : ""}`;
  const origen = t.origen === "medido" ? `medido en el escenario «${t.escenario ?? ""}»` : "estimado a mano, sin escenario que lo mueva";
  return { cifras, origen };
}
