import type { ZonaOut } from "../types";
import { ACABADOS, acabadoDeColor } from "../viewport/acabados";
import type { MandoVivo } from "./protocolo";

/* Cada mando del tablero → el mensaje de acción del WebSocket (plan V8.4 D4; Bitácora de F0
   § «Qué cambia…», punto 3). Como el real:
   - pulsador con resorte: bajar el mouse = `pulsar` (sin `durante_s`), soltarlo = `soltar`;
     el mantenido alterna con cada pulsación y al soltar no pasa nada;
   - seta: `presionar` la deja RETENIDA; otro clic la `libera` (ISO 13850);
   - seccionador y resguardo: `abrir` / `cerrar`; selector: `girar` a una posición;
     potenciómetro: `girar` con 0–1.
   Puro: lo usan el panel «Mandos» y el clic en la pieza 3D. */

export type Accion = Record<string, string | number>;

/** El estado que hace falta para decidir el mensaje: lo lee quien llama de las señales. */
export interface EstadoMando {
  /** La seta está retenida (`<des>.accionado`). */
  retenida?: boolean;
  /** El seccionador (o el resguardo) está cerrado (`<des>.cerrado`). */
  cerrado?: boolean;
  /** El actuador de un pulsador con varios (`marcha`, `paro`). */
  actuador?: string;
}

function base(accion: string, m: MandoVivo, actuador?: string): Accion {
  const out: Accion = { accion, dispositivo: m.designacion };
  if (actuador && (m.actuadores?.length ?? 0) > 1) out.actuador = actuador;
  return out;
}

/** Bajar el mouse (o la tecla) sobre el mando. null: este mando no hace nada así. */
export function alApretar(m: MandoVivo, e: EstadoMando = {}): Accion | null {
  switch (m.tipo) {
    case "pulsador":
      return base("pulsar", m, e.actuador); // voseo-interno
    case "seta":
      return base(e.retenida ? "liberar" : "presionar", m);
    case "seccionador":
    case "resguardo":
      return base(e.cerrado === false ? "cerrar" : "abrir", m);
    default:
      return null;
  }
}

/** Soltar el mouse: sólo un pulsador con resorte vuelve. */
export function alSoltar(m: MandoVivo, e: EstadoMando = {}): Accion | null {
  if (m.tipo === "pulsador" && (m.retorno ?? "resorte") === "resorte") return base("soltar", m, e.actuador);
  return null;
}

/** Girar un selector a una posición, o el potenciómetro de un pulsador a 0–1. */
export function girar(m: MandoVivo, valor: string | number): Accion {
  const v = typeof valor === "number" ? Math.min(1, Math.max(0, valor)) : valor;
  return { accion: "girar", dispositivo: m.designacion, valor: v };
}

/** Un pulsador se mantiene apretado mientras dura el clic (su soltar importa). */
export function esMomentaneo(m: MandoVivo): boolean {
  return m.tipo === "pulsador" && (m.retorno ?? "resorte") === "resorte";
}

const NOMBRES: Record<string, string> = {
  pulsador: "Pulsador",
  seta: "Seta de emergencia",
  selector: "Selector",
  seccionador: "Seccionador",
  resguardo: "Resguardo",
};

/** Cómo se llama el tipo de mando en pantalla. */
export function nombreTipo(m: MandoVivo): string {
  return NOMBRES[m.tipo] ?? "Mando";
}

/** El tipo con su estado, para los que se quedan como los dejas: «Resguardo abierto», «Seta de
 *  emergencia presionada» (el estado en texto, no sólo en la tapa); sin señal todavía, o en un
 *  pulsador, sólo el tipo. */
export function nombreConEstado(m: MandoVivo, e: EstadoMando = {}): string {
  const tipo = nombreTipo(m);
  if (m.tipo === "seta" && e.retenida !== undefined) return `${tipo} ${e.retenida ? "presionada" : "liberada"}`;
  if ((m.tipo !== "seccionador" && m.tipo !== "resguardo") || e.cerrado === undefined) return tipo;
  return `${tipo} ${e.cerrado ? "cerrado" : "abierto"}`;
}

/** El rótulo del botón según lo que va a hacer. */
export function rotuloAccion(m: MandoVivo, e: EstadoMando = {}): string {
  switch (m.tipo) {
    case "pulsador":
      return m.retorno === "mantenido" ? "Alternar" : "Presionar"; // el mismo verbo que la seta
    case "seta":
      return e.retenida ? "Liberar" : "Presionar";
    case "seccionador":
    case "resguardo":
      return e.cerrado === false ? "Cerrar" : "Abrir";
    default:
      return "Accionar";
  }
}

/* Color FÍSICO de un mando o un piloto (excepción acotada de color, ui/CLAUDE.md): el del
   aparato real según su ficha de catálogo (`specs.color`). Nunca un color de estado. Sale del
   ACABADO de ese color (`apariencia.ACABADO_DE_COLOR` → su albedo en `acabados.json`): el mismo
   tono con que el visor pinta la lente o el botón, sin tabla de tonos propia. */

/** El color CSS de un color físico del catálogo (el albedo de su acabado); null si no tiene o
 *  la tabla de acabados no lo conoce. */
export function colorFisico(nombre: string | null | undefined): string | null {
  const clave = acabadoDeColor(nombre);
  return clave ? ACABADOS[clave].color : null;
}

/* El piloto ENCENDIDO en el 3D, regla escrita (y la única que cambia el tono del acabado):
   emite el MISMO albedo del acabado de su color con intensidad `EMISION_PILOTO`, y sólo en su
   zona de color (la lente: la zona `de_color` que marca el servidor). Apagado no emite: se ve
   el acabado tal cual. Un piloto sin color conocido brilla en el blanco (`plastico_blanco`). */
export const EMISION_PILOTO = 1.6;

/** El tono con que brilla un piloto encendido: el de su color físico o, si no se conoce, el blanco. */
export function tonoEncendido(color: string | null | undefined): string {
  return colorFisico(color) ?? colorFisico("blanco")!; // «blanco» está en la tabla (mandos.test.ts)
}

/** Qué materiales de la pieza de un piloto se encienden (índices en su arreglo de materiales,
 *  el de las zonas: uno por zona, en su orden). Sólo los de la zona de color si la malla está
 *  partida por esas zonas y alguna lo es; si no (sin zonas, taladrada, servidor anterior sin
 *  `de_color`), todos: la pieza entera, como antes. */
export function materialesQueBrillan(zonas: readonly ZonaOut[] | undefined, nMateriales: number): number[] {
  const todos = Array.from({ length: nMateriales }, (_, i) => i);
  if (!zonas || zonas.length !== nMateriales) return todos;
  const deColor = zonas.flatMap((z, i) => (z.de_color ? [i] : []));
  return deColor.length ? deColor : todos;
}

/** Un piloto está encendido con su señal ≥ 0,5 (las booleanas llegan como 0/1). */
export function encendido(valor: number | undefined): boolean {
  return valor !== undefined && Number.isFinite(valor) && valor >= 0.5;
}

/** «Provocar atasco» frena una junta MOTRIZ con un par: sólo si la máquina tiene un motor o una
 *  banda (un cilindro neumático no se atasca con un par: V8.9 F6). */
export function hayAtasco(ini: { bandas: unknown[]; dispositivos: { tipo: string }[] }): boolean {
  return ini.bandas.length > 0 || ini.dispositivos.some((d) => d.tipo === "motor");
}

/** La junta que frena «Provocar atasco»: la que mueve la banda (la primera), o la primera junta. */
export function juntaMotriz(ini: { bandas: { junta: string }[]; juntas: { name: string }[] }): string | null {
  return ini.bandas[0]?.junta ?? ini.juntas[0]?.name ?? null;
}
