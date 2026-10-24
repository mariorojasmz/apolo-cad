import type { CadenaSerie, FajaSerie } from "../viewport/marcha/serie";

/* El protocolo de `WS /api/cosim/vivo` (plan V8.4 D2; tabla en la Bitácora de F1 y en
   `core/apolo/cosim/vivo_fotograma.py`): los tipos del primer mensaje (`inicio`), la lectura de
   los JSON cortos y del fotograma binario, y el texto para la persona de cada cierre. Puro: sin
   WebSocket ni three.js (se prueba en node). */

/** Un mando del tablero (pulsador, seta, selector, seccionador) como lo publica el `inicio`. */
export interface MandoVivo {
  designacion: string;
  tipo: string;
  ref: string;
  acciones: string[];
  /** Color FÍSICO del catálogo («verde», «rojo»…); la seta trae además `fondo` (amarillo). */
  color: string | null;
  fondo?: string;
  /** La pieza 3D ligada (id de la escena): se aprieta también con clic en el 3D. */
  pieza?: string;
  retorno?: "resorte" | "mantenido";
  actuadores?: string[];
  potenciometro?: boolean;
  posiciones?: string[];
  senales: string[];
}

export interface PilotoVivo {
  designacion: string;
  ref: string;
  color: string | null;
  pieza?: string;
  /** `<des>.encendido`: 1 encendido, 0 apagado. */
  senal: string;
}

export interface DispositivoVivo {
  designacion: string;
  tipo: string;
  ref: string;
  pieza?: string;
}

/** Una falla que un aparato sabe tomar (plan cosim-fallas D6): `pide` dice qué valor lleva
 *  (`""`, `bool`, `bool?`, `posicion?`, `unidad?`, `borne,valor`, `canal`; `modelos/base.PIDE`). */
export interface FallaCatalogo {
  falla: string;
  pide: string;
  /** Lo que se puede elegir como valor: posiciones, bornes, canales, unidades. */
  opciones?: (string | number)[];
}

export interface AparatoFallas {
  designacion: string;
  tipo: string;
  fallas: FallaCatalogo[];
}

/** Un contacto (o un conductor con largo) que se puede pegar o cortar (D3, D6). */
export interface RamaVivo {
  id: string;
  tipo: "contacto" | "conductor" | string;
  red: string;
  dispositivo?: string;
}

export interface InicioVivo {
  tipo: "inicio";
  version: number;
  proyecto: number | null;
  escenario: string;
  firma: string;
  ventana_s: number;
  max_s: number;
  ritmo: number;
  dt_s: number;
  formato: number;
  cuerpos: { name: string; junta: string; piezas: string[] }[];
  productos: { name: string; producto: string; dims_mm: [number, number, number] }[];
  juntas: { name: string; tipo: string; unidad: string }[];
  bandas: { pieza: string; junta: string; radio_mm: number; direccion: [number, number, number] }[];
  senales: string[];
  mandos: MandoVivo[];
  pilotos: PilotoVivo[];
  dispositivos: DispositivoVivo[];
  fajas: FajaSerie[];
  cadenas: CadenaSerie[];
  avisos: string[];
  /** Lo que se puede hacer fallar (cosim-fallas D6); un servidor anterior no lo trae. */
  fallas?: AparatoFallas[];
  ramas?: RamaVivo[];
}

/** Los JSON cortos que llegan después del `inicio` (los que la UI usa). */
export type MensajeVivo =
  | InicioVivo
  | { tipo: "senales"; desde: number; nombres: string[] }
  | { tipo: "textos"; t: number; valores: Record<string, unknown> }
  | { tipo: "ack"; id: string | null; t: number; evento?: Record<string, unknown> }
  | { tipo: "rechazo"; id: string | null; motivo: string }
  | { tipo: "factor"; lento: boolean; factor: number }
  | { tipo: "sesion_vieja"; vieja: boolean; mensaje?: string }
  | { tipo: "pausa"; t: number }
  | { tipo: "reanudar"; t: number }
  | { tipo: "fin"; motivo: string; t?: number; mensaje?: string }
  | { tipo: "error"; codigo: string; motivo: string };

const TIPOS = new Set(["inicio", "senales", "textos", "ack", "rechazo", "factor", "sesion_vieja",
  "pausa", "reanudar", "fin", "error"]);

/** Un mensaje de texto del WebSocket, o null si no es JSON o es de un tipo que no conocemos. */
export function leerMensaje(texto: string): MensajeVivo | null {
  let m: unknown;
  try {
    m = JSON.parse(texto);
  } catch {
    return null;
  }
  if (!m || typeof m !== "object") return null;
  const tipo = (m as { tipo?: unknown }).tipo;
  if (typeof tipo !== "string" || !TIPOS.has(tipo)) return null;
  if (tipo === "inicio") {
    const i = m as Partial<InicioVivo>;
    if (!Array.isArray(i.cuerpos) || !Array.isArray(i.senales) || !Array.isArray(i.mandos)) return null;
  }
  if (tipo === "senales") {
    const s = m as { desde?: unknown; nombres?: unknown };
    if (typeof s.desde !== "number" || !Array.isArray(s.nombres)) return null;
  }
  return m as MensajeVivo;
}

// ── el fotograma binario ─────────────────────────────────────────────────────────────────────

export const FORMATO = 1;
export const CABECERA = 8;

export interface Fotograma {
  t: number;
  factor: number;
  nc: number;
  np: number;
  nj: number;
  nb: number;
  ns: number;
  /** nc × 7: cada cuerpo relativo a su pose inicial (x, y, z mm, qx, qy, qz, qw). */
  cuerpos: Float32Array;
  /** np × 7: el centro de cada producto en absoluto; NaN si no está en el mundo. */
  productos: Float32Array;
  juntas: Float32Array;
  bandas: Float32Array;
  /** ns valores en el orden de la tabla de señales; NaN si ese intercambio no la trae. */
  senales: Float32Array;
}

const LITTLE_ENDIAN = new Uint8Array(new Uint16Array([1]).buffer)[0] === 1;

function flotantes(buf: ArrayBuffer): Float32Array {
  if (LITTLE_ENDIAN) return new Float32Array(buf, 0, buf.byteLength >> 2);
  const v = new DataView(buf);
  const out = new Float32Array(buf.byteLength >> 2);
  for (let i = 0; i < out.length; i++) out[i] = v.getFloat32(i * 4, true);
  return out;
}

/** El fotograma float32 little-endian de la sesión viva, o null si no es del formato 1 o viene
 *  cortado. Las partes son VISTAS sobre el mismo buffer (no se copian). */
export function decodificarFotograma(buf: ArrayBuffer): Fotograma | null {
  if (buf.byteLength < CABECERA * 4 || buf.byteLength % 4) return null;
  const a = flotantes(buf);
  if (a[0] !== FORMATO) return null;
  const [nc, np, nj, nb, ns] = [a[3], a[4], a[5], a[6], a[7]].map((x) => Math.max(0, Math.round(x)));
  const largo = CABECERA + 7 * (nc + np) + nj + nb + ns;
  if (a.length < largo) return null;
  let i = CABECERA;
  const parte = (n: number) => {
    const p = a.subarray(i, i + n);
    i += n;
    return p;
  };
  return {
    t: a[1], factor: a[2], nc, np, nj, nb, ns,
    cuerpos: parte(7 * nc), productos: parte(7 * np), juntas: parte(nj), bandas: parte(nb),
    senales: parte(ns),
  };
}

// ── los cierres, para la persona ─────────────────────────────────────────────────────────────

export interface ProblemaVivo {
  texto: string;
  /** El motivo del servidor, para el «Detalle técnico». */
  detalle?: string;
  /** 4423: hay otra sesión abierta y se puede reemplazar desde aquí. */
  reemplazable?: boolean;
}

/** Qué pasó y qué hacer, por el código de cierre del WebSocket (y el motivo que mandó antes). */
export function problemaDeCierre(codigo: number, motivo?: string, escenario?: string): ProblemaVivo {
  const detalle = motivo || undefined;
  switch (codigo) {
    case 4401:
      return { texto: "No pudimos saber qué proyecto está abierto. Abre la sesión viva de nuevo.", detalle };
    case 4403:
      return { texto: "El servidor no acepta la sesión viva desde esta página. Abre Apolo desde su dirección de siempre.", detalle };
    case 4409:
      return { texto: "El proyecto abierto cambió mientras se abría la sesión. Ábrela de nuevo.", detalle };
    case 4400:
      return {
        texto: `El escenario ${escenario ? `«${escenario}» ` : ""}no se puede simular en vivo. Elige otro o pídele al agente que lo revise.`,
        detalle,
      };
    case 4423:
      return {
        texto: "Ya hay otra sesión viva abierta (en otra pestaña o ventana). Ciérrala, o reemplázala desde aquí.",
        detalle, reemplazable: true,
      };
    case 4500:
      return { texto: "La simulación se detuvo por un error. Abre la sesión de nuevo.", detalle };
    default:
      return { texto: "Se perdió la conexión con el servidor. Revisa que Apolo siga abierto y abre la sesión de nuevo.", detalle };
  }
}

/** Por qué terminó una sesión (el `motivo` del mensaje `fin`). */
export function textoFin(motivo: string | undefined): string {
  switch (motivo) {
    case "parada":
      return "Paraste la sesión.";
    case "tope":
      return "La sesión llegó a su tiempo máximo.";
    case "reemplazada":
      return "Se abrió otra sesión viva y esta se cerró.";
    case "cerrada":
      return "La sesión se cerró.";
    default:
      return "La simulación terminó por un error.";
  }
}
