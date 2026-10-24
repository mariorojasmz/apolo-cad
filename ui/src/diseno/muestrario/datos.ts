import type { ItemAtencion } from "../atencion";
import { cifra } from "../cifra";

/* Datos de EJEMPLO del panel «Tablero» (plan V8.5 F3b), para el muestrario y los tests de
   `diseno/`: todavía no hay tablero armado. F3b los reemplaza por lo que devuelve
   `services/tablero.py`. Cada ítem señala una pieza del 3D de ejemplo (`VueloDemo.tsx`). */

/** La pieza que señala cada ítem del ejemplo. */
export const PIEZA_DE: Record<string, string> = {
  puerta: "puerta",
  canaleta: "canaleta-h",
  prensa: "prensaestopas",
};

export function itemsTablero(ir: (pieza: string) => void): ItemAtencion[] {
  return [
    { clave: "canaleta", severidad: "aviso", frase: "La canaleta de arriba va muy llena", cifra: cifra(64, 0, "%"), accion: () => ir(PIEZA_DE.canaleta) },
    { clave: "calor", severidad: "sin_evaluar", frase: "Falta evaluar el calentamiento" },
    { clave: "puerta", severidad: "falla", frase: "La puerta choca con la seta al abrir", cifra: cifra(3, 0, "mm"), accion: () => ir(PIEZA_DE.puerta) },
    { clave: "prensa", severidad: "aviso", frase: "El prensaestopas del motor es chico", cifra: "M16", accion: () => ir(PIEZA_DE.prensa) },
    { clave: "largos", severidad: "bien", frase: "Todos los conductores tienen recorrido", cifra: cifra(38, 0) },
  ];
}

export const ITEMS_TABLERO: ItemAtencion[] = itemsTablero(() => {});
