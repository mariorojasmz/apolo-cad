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

export interface CalentamientoTablero {
  estado: "sin_evaluar";
  motivo: string;
  perdidas_W: number;
  sin_dato: string[];
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
    calentamiento: CalentamientoTablero;
    supuestos: string[];
  };
}

export interface TablerosOut {
  tableros: { ubicacion: string; comando: string; armado: boolean }[];
}
