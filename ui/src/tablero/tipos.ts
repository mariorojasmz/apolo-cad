import type { Severidad } from "../diseno/atencion";

/* Lo que devuelve `GET /api/tablero/{ubicacion}` (plan V8.5 D13, D15): `services/tablero_panel.py`
   es la única fuente; la UI no decide ninguna regla, sólo la muestra. Coordenadas en mm de mundo. */

export interface ItemTablero {
  clave: string;
  severidad: Severidad;
  frase: string;
  /** La cifra que lo prueba; la UI la escribe con `cifra()`. */
  valor?: number;
  unidad?: string;
  decimales?: number;
  /** Las piezas que señala (la cámara las encuadra y las selecciona). */
  piezas: string[];
  /** Los conductores que toca (uno: se dibuja; varios: se listan en el detalle). */
  conductores: string[];
  /** Una frase más, para la persona: aparece al elegir el ítem. */
  detalle?: string;
  /** Texto crudo del servidor (plegado en «Detalle técnico»). */
  tecnico?: string;
}

export interface ConductorTablero {
  id: string;
  puntos: string[];
  /** El que se compra: el escrito a mano manda. */
  largo_m: number;
  origen: "ruteo" | "declarado";
  ruteado_m: number;
  declarado_m?: number;
  sale?: boolean;
  cable?: string;
  piezas: string[];
  /** Una polilínea por tramo, en mm de mundo (con la puerta cerrada). */
  recorrido?: number[][][];
}

/** Un cable de CAMPO que sale del tablero (F4b): `services/tablero_cables.py` sobre
   `cables_campo.vista`. Sin recorrido completo, `incompleto` (y sin largo si no se calculó). */
export interface CableTablero {
  /** El comando del cable: el mismo espacio de ids que los conductores (se dibuja igual). */
  id: string;
  designacion: string;
  ref: string;
  nombre?: string;
  calculado: boolean;
  /** Dentro + afuera + reserva. */
  largo_m?: number;
  partes_m?: { adentro: number; afuera: number; reserva: number };
  declarado_m?: number;
  supuestos?: string[];
  incompleto?: boolean;
  /** Lo que gira y toca o roza (la cámara las encuadra). */
  piezas: string[];
  /** UN tramo: la polilínea en mm de mundo, del tablero al aparato. */
  recorrido?: number[][][];
}

export interface CanaletaTablero {
  nombre: string;
  pieza: string | null;
  orientacion: "h" | "v";
  /** Fracción de la sección útil (0,13 = 13 %). */
  llenado: number;
  ocupado_mm2: number;
  util_mm2: number | null;
  conductores: number;
}

export interface AparatoTablero {
  designacion: string;
  ref: string;
  nombre: string;
  zona: string;
  fila: string;
  pieza?: string;
}

/** El calentamiento por IEC 60890 (V8.5 F3): `bien`/`falla` con las temperaturas, o `sin_evaluar`
   con su `motivo` (fuera del método o sin temperaturas máximas). */
export interface CalentamientoTablero {
  estado: "bien" | "falla" | "sin_evaluar";
  motivo?: string;
  perdidas_W: number;
  perdidas?: { aparatos_W: number; conductores_W: number };
  sin_dato: string[];
  ambiente_C?: number;
  ventilacion_m3h?: number;
  T_media_C?: number;
  T_arriba_C?: number;
  peor?: { designacion: string; T_C: number; T_max_C: number };
  sugerencia?: { caudal_m3h?: number; refrigeracion?: boolean };
}

/** El prensaestopas de un cable que sale (V8.5 F3, D7): su ref, o el motivo si ninguno lo sujeta. */
export interface PrensaTablero {
  cable: string;
  designacion: string;
  diametro_mm?: number;
  ref?: string;
  rosca?: string;
  nombre?: string;
  motivo?: string;
}

export interface PanelTableroOut {
  ubicacion: string;
  comando: string;
  armado: boolean;
  gabinete?: { ref: string; nombre: string; pieza: string; medidas_mm: number[] };
  veredicto: { severidad: Severidad; frase: string; nota?: string };
  items: ItemTablero[];
  puerta?: { junta: string; pieza: string; min_deg: number; max_deg: number; bisagra: string };
  detalle?: {
    bien: ItemTablero[];
    aparatos: AparatoTablero[];
    canaletas: CanaletaTablero[];
    conductores: ConductorTablero[];
    /** Los cables de campo que salen de él (vacía sin `por`). */
    cables?: CableTablero[];
    calentamiento: CalentamientoTablero;
    prensaestopas?: { cara: string; prensas: PrensaTablero[] };
    supuestos: string[];
  };
}

export interface TablerosOut {
  tableros: { ubicacion: string; comando: string; armado: boolean }[];
}
