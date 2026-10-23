/* Paleta CATEGÓRICA de datos de Apolo (plan V8.4 D6): el color de cada señal del osciloscopio
   (identidad, nunca estado). Es la paleta de referencia de la guía de dataviz, en su ORDEN fijo
   (el orden es lo que la hace distinguible con daltonismo: los vecinos se separan):
   - oscuro: validada contra el fondo de los paneles de Apolo (`--panel` #1e222b) con
     `validate_palette.js --mode dark --surface #1e222b`: todo PASA (banda de luminosidad, croma,
     CVD entre vecinos ΔE 8,4, visión normal ΔE 19,3, contraste ≥ 3:1).
   - claro: la misma, con los pasos para fondo claro (#fcfcfb): pasa, con contraste < 3:1 en
     aqua, amarillo y magenta → exige rótulo visible (el osciloscopio rotula cada carril).
   Apolo hoy tiene sólo el tema oscuro; la columna clara queda lista para cuando haya otro.
   Una novena señal no inventa un color: el osciloscopio admite 8 (`MAX_SENALES`). El texto
   nunca lleva el color de la serie: va en la tinta del tema, con una muestra de color al lado. */

export const PALETA_OSCURO = [
  "#3987e5", // azul
  "#d95926", // naranja
  "#199e70", // aqua
  "#c98500", // amarillo
  "#d55181", // magenta
  "#008300", // verde
  "#9085e9", // violeta
  "#e66767", // rojo
] as const;

export const PALETA_CLARO = [
  "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948",
] as const;

/** El color de la posición `i` de la paleta (la del tema de Apolo: oscuro). */
export function colorDato(i: number): string {
  return PALETA_OSCURO[((i % PALETA_OSCURO.length) + PALETA_OSCURO.length) % PALETA_OSCURO.length];
}
