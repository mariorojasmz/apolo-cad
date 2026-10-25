import type { Severidad } from "../diseno/atencion";
import type { ItemTablero } from "../tablero/tipos";

/* Lo que devuelve `GET /api/neumatica` (plan V8.9 D12): `services/neumatica_panel.py` es la única
   fuente (sobre el ERC y la memoria del aire, los mismos que lee el agente); la UI no decide
   ninguna regla. El esquema llega en primitivas en mm, con la Y hacia abajo (la del SVG). */

/** Un ítem: la misma forma que los del panel «Tablero» (sin conductores). */
export type ItemNeumatica = ItemTablero;

/** De qué señal de la sesión viva sale la presión de una línea (`services/neumatica_vista.py`). */
export interface PresionLinea {
  senal?: string;
  /** Sólo con esta señal en 1 (la válvula de corte abierta); si no, 0 bar. */
  si?: string;
  /** Una vía de trabajo: según la posición de la válvula, la alimentación, un escape o cerrada. */
  valvula?: string;
  tabla?: Record<string, string | null>;
  alimentacion?: PresionLinea;
  atmosfera?: boolean;
}

export interface SimboloEsquema {
  designacion: string;
  tipo: string;
  /** [x, y, ancho, alto] en mm. */
  caja: number[];
  /** Las piezas del aparato en el 3D (la ligada primero); vacía si no está ligado. */
  piezas: string[];
  /** Lo que es, para la persona: «Cilindro Ø32 mm, vástago 12 mm, carrera 200 mm». */
  rotulo?: string;
  /** A qué borne del tablero llega cada bobina («A1: +TAB1-S2:14»). */
  bornes?: string[];
}

export interface LineaEsquema {
  id: string;
  puertos: string[];
  /** [x1, y1, x2, y2] de cada tramo. */
  tramos: number[][];
  presion: PresionLinea;
}

export interface ValvulaEsquema {
  designacion: string;
  tipo: string | null;
  /** `<des>.posicion` (texto «14», «12», «0») o `<des>.abierta` (0/1) de la válvula de corte. */
  senal: string;
  /** La caja [x, y, ancho, alto] de cada posición. */
  cajas: Record<string, number[]>;
}

export interface EsquemaNeumatico {
  /** Sin esquema: qué falta (el texto de la lámina). */
  error?: string;
  vista: number[];
  /** [x1, y1, x2, y2, a trazos (1) o lleno (0)]. */
  trazos: number[][];
  /** [x, y, r, lleno]. */
  circulos: number[][];
  poligonos: { puntos: number[][]; lleno: boolean }[];
  /** `rotulo`: las designaciones (van en el SVG, con un piso de tamaño); `detalle`: lo que la lámina
   *  escribe a 2 mm (se lee al elegir el aparato). */
  textos: { x: number; y: number; texto: string; alto: number; anclaje: "start" | "middle" | "end"; clase?: "rotulo" | "detalle" }[];
  simbolos: SimboloEsquema[];
  lineas: LineaEsquema[];
  valvulas: ValvulaEsquema[];
  /** El tope de la escala de colores de la presión (bar). */
  escala_bar: number;
  avisos: string[];
}

export interface CilindroDetalle {
  designacion: string;
  ref: string;
  piezas: string[];
  diametro_mm?: number;
  vastago_mm?: number;
  carrera_mm?: number;
  fuerza?: { F_avance_N: number; F_avance_ef_N: number; F_retroceso_N: number; F_retroceso_ef_N: number; p_bar: number };
  consumo?: { ciclo_NL: number; NL_min?: number; ciclos_min?: number };
  tiempo?: { origen: "medido" | "estimado"; escenario?: string; avance_s: number; retroceso_s?: number | null };
}

export interface PanelNeumaticaOut {
  hay_aire: boolean;
  veredicto?: { severidad: Severidad; frase: string; nota?: string };
  items?: ItemNeumatica[];
  detalle?: { cilindros: CilindroDetalle[]; maquina: { NL_min?: number; sin_fugas_NL_min?: number } };
  esquema?: EsquemaNeumatico;
}
