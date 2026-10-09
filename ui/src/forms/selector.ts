/* Valor de un campo selector de caras/aristas (EdgeSelector del backend): sus modos, cómo se
   normaliza para la API y qué guarda el clic en el viewport. Puro: lo pinta `SchemaForm`. */

export type SelectorValue = {
  mode: string;
  direction?: string;
  face?: string;
  min?: number | string;
  max?: number | string;
  point?: number[];
  count?: number;
  medir?: string; // cerca: sin la clave = al centro (selecciones guardadas) | "superficie" (el clic)
  entidad?: string; // mates: cara | arista | ancla (sin widget propio, pero no se pierde al editar)
  name?: string; // modo "ancla": nombre del frame publicado por el componente
};

// Etiquetas de los modos del selector. La LISTA de modos sale del enum del schema
// (EdgeSelector.mode) para no desincronizarse del backend; un modo sin etiqueta se
// muestra por su clave. El fallback solo aplica si el schema no trae el enum.
export const SELECTOR_MODE_LABELS: Record<string, string> = {
  todas: "Todas",
  direccion: "Por dirección",
  cara: "Por cara",
  longitud: "Por longitud",
  cerca: "Cerca de un punto",
  ancla: "Por ancla (nombre)",
};
export const SELECTOR_MODES_FALLBACK = Object.keys(SELECTOR_MODE_LABELS);
export const SELECTOR_FACES_FALLBACK = ["tope", "base", "min_x", "max_x", "min_y", "max_y"];

export function normalizeSelector(v: SelectorValue): SelectorValue {
  const out: SelectorValue = { mode: v.mode };
  if (v.mode === "direccion") out.direction = v.direction ?? "z";
  if (v.mode === "cara") out.face = v.face ?? "tope";
  if (v.mode === "longitud") {
    if (v.min !== undefined && String(v.min).trim() !== "") out.min = Number(v.min);
    if (v.max !== undefined && String(v.max).trim() !== "") out.max = Number(v.max);
  }
  if (v.mode === "cerca") {
    out.point = v.point;
    out.count = v.count ?? 1;
    if (v.medir) out.medir = v.medir; // una selección guardada sin `medir` sigue sin él
  }
  if (v.mode === "ancla") out.name = (v.name ?? "").trim();
  if (v.entidad) out.entidad = v.entidad;
  return out;
}

/** Lo que guarda un clic en el viewport: `cerca` del punto clicado midiendo a la SUPERFICIE.
 *  El punto está sobre la cara que la persona tocó; medido al centro podía ganar un taladro
 *  vecino (plan fea-chapa-empernada, D6). Conserva `count` y `entidad` de la selección previa. */
export function seleccionDelClic(point: readonly number[], prev: SelectorValue | null): SelectorValue {
  return { mode: "cerca", point: [...point], count: prev?.count ?? 1, medir: "superficie", entidad: prev?.entidad };
}
