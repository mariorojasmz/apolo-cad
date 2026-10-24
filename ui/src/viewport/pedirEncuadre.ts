/* El pedido de encuadre que otros paneles le hacen al viewport (`apolo:fit`, ui/CLAUDE.md
   § Shell y paneles), sin acoplarse a three.js. Por defecto el encuadre SALTA y no toca la
   selección, como siempre; un panel nuevo (el «Tablero» de V8.5) pide `animar` (la cámara
   vuela) y `seleccionar` (las piezas quedan con el contorno de selección). */

export interface OpcionesEncuadre {
  /** La cámara vuela ≈ 320 ms en vez de saltar (con movimiento reducido, salta igual). */
  animar?: boolean;
  /** Selecciona las piezas pedidas que estén a la vista: se ven con el contorno de siempre. */
  seleccionar?: boolean;
}

/** Pide encuadrar esas piezas (vacío = la selección o el modelo entero). */
export function pedirEncuadre(ids: readonly string[], opciones: OpcionesEncuadre = {}): void {
  window.dispatchEvent(new CustomEvent("apolo:fit", { detail: { ids: [...ids], ...opciones } }));
}

/** Las opciones de un `detail` de `apolo:fit`: sólo un `true` explícito las prende. */
export function opcionesDelEncuadre(detail: unknown): Required<OpcionesEncuadre> {
  const d = (detail ?? {}) as { animar?: unknown; seleccionar?: unknown };
  return { animar: d.animar === true, seleccionar: d.seleccionar === true };
}
