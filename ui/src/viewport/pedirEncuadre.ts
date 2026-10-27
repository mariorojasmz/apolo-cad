/* El pedido de encuadre que otros paneles le hacen al viewport (`apolo:fit`, ui/CLAUDE.md
   § Shell y paneles), sin acoplarse a three.js. Por defecto el encuadre SALTA y no toca la
   selección, como siempre; un panel nuevo (el «Tablero» de V8.5) pide `animar` (la cámara
   vuela) y `seleccionar` (las piezas quedan con el contorno de selección). Todo encuadre centra
   en lo que se VE del visor, sin el panel lateral (plan visor-para-evaluar D13); `frente` mira
   la cara grande de una pieza de frente (D14) y `despejar` esquiva o atenúa lo que tapa (D15). */

export interface OpcionesEncuadre {
  /** La cámara vuela ≈ 320 ms en vez de saltar (con movimiento reducido, salta igual). */
  animar?: boolean;
  /** Selecciona las piezas pedidas que estén a la vista: se ven con el contorno de siempre. */
  seleccionar?: boolean;
  /** Puntos (mm de mundo) que el encuadre también tiene que mostrar: el recorrido de un conductor
   *  del panel «Tablero» (V8.5 F3b), que no es una pieza. */
  puntos?: readonly (readonly number[])[];
  /** Una pieza cuya cara grande se mira DE FRENTE (la puerta de un tablero): la cámara se pone
   *  sobre su normal, hacia afuera de lo encuadrado, y la caja crece lo que la pieza abre. */
  frente?: string;
  /** Si otra pieza tapa lo encuadrado: probar vistas cercanas y, si no hay una libre, atenuar
   *  lo que tapa (vuelve con el próximo encuadre o con `apolo:restaurar-atenuadas`). */
  despejar?: boolean;
}

/** Pide encuadrar esas piezas (vacío = la selección o el modelo entero). */
export function pedirEncuadre(ids: readonly string[], opciones: OpcionesEncuadre = {}): void {
  window.dispatchEvent(new CustomEvent("apolo:fit", { detail: { ids: [...ids], ...opciones } }));
}

/** Las opciones de un `detail` de `apolo:fit`: sólo un `true` explícito las prende; de `puntos`,
   sólo los [x, y, z] finitos. */
export function opcionesDelEncuadre(detail: unknown): Required<OpcionesEncuadre> {
  const d = (detail ?? {}) as { animar?: unknown; seleccionar?: unknown; puntos?: unknown; frente?: unknown; despejar?: unknown };
  const puntos = Array.isArray(d.puntos)
    ? d.puntos.filter((p): p is number[] => Array.isArray(p) && p.length === 3 && p.every((x) => Number.isFinite(x)))
    : [];
  return {
    animar: d.animar === true, seleccionar: d.seleccionar === true, puntos,
    frente: typeof d.frente === "string" ? d.frente : "", despejar: d.despejar === true,
  };
}
