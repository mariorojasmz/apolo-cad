import type { Severidad } from "../diseno/atencion";

/* Lo que manda `GET /api/pruebas` y `GET /api/pruebas/{nombre}` (`services/pruebas_panel.py`,
   plan visor-para-evaluar D1–D4): el panel lo muestra sin reglas propias. */

export interface FilaPrueba {
  nombre: string;
  /** El estado crudo (`pasa`, `falla`, `vencido`, `sin_aserciones`, `sin_correr`): sólo para la lógica. */
  estado: string;
  /** Cómo se dice el estado: «Pasa», «Vencido»… */
  rotulo: string;
  severidad: Severidad;
  descripcion?: string;
  /** Vencido: por qué ya no vale y qué dio la última vez. */
  motivo?: string;
  ultimo?: string;
  /** ISO local de la última corrida. */
  fecha?: string;
  /** «12 entraron · 12 rampa · 0 trabados». */
  balance?: string;
  /** Lo que tardó la última corrida (s de reloj): cuánto esperar al correrla. */
  estimado_s?: number;
  n_fallidas?: number;
}

export interface PanelPruebasOut {
  veredicto: { severidad: Severidad; frase: string } | null;
  escenarios: FilaPrueba[];
}

export interface Incidencia {
  tipo: "trabados" | "perdidos" | "retenidos" | "sin_entrar";
  producto?: string;
  /** «trabado», «cayó al piso»… */
  que?: string;
  hora_s?: number;
  punto_mm?: number[];
  pieza?: string;
  cerca_de?: string;
  /** Las que no vinieron en la lista (recortada): cuántas más hay. */
  mas?: number;
}

export interface DetallePrueba extends FilaPrueba {
  fallidas: { asercion: string; cifra: string }[];
  incidencias: Incidencia[];
  n_aserciones: number;
}
