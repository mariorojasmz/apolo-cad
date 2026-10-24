/* Lo que pide atención en un panel con veredicto (plan V8.5 D13–D14, F3b-0): cada ítem es una
   frase y su cifra, con una severidad. El veredicto sale de los ítems: sin ninguno, la frase de
   «está bien» que da el panel; con alguno, cuántas cosas hay que mirar. Puro: lo usan
   `<Veredicto>` y `<ItemsAtencion>`, y el panel «Tablero» de F3b le pasa sus datos. */

/** `falla`: no cumple, hay que corregir. `aviso`: conviene revisar. `sin_evaluar`: faltan datos
   para juzgar (nunca un número inventado). `bien`: cumple. */
export type Severidad = "falla" | "aviso" | "sin_evaluar" | "bien";

export interface ItemAtencion {
  /** Clave estable de React. */
  clave: string;
  severidad: Severidad;
  /** Qué pasa, en una frase: «La canaleta horizontal va muy llena». */
  frase: string;
  /** La cifra que lo prueba, ya con unidad (`cifra()`): «64 %». */
  cifra?: string;
  /** Lo que hace el clic: encuadrar la pieza, abrir el detalle. Sin acción, no es botón. */
  accion?: () => void;
}

/** Cómo se dice la severidad, para quien no ve el ícono (lector de pantalla, daltonismo). */
export const ROTULO_SEVERIDAD: Record<Severidad, string> = {
  falla: "Para corregir",
  aviso: "Para revisar",
  sin_evaluar: "Sin evaluar",
  bien: "Cumple",
};

const PESO: Record<Severidad, number> = { falla: 0, aviso: 1, sin_evaluar: 2, bien: 3 };

/** Lo más grave primero; a igual severidad, el orden en que llegaron. */
export function ordenarItems<T extends { severidad: Severidad }>(items: readonly T[]): T[] {
  return items.map((it, i) => ({ it, i }))
    .sort((a, b) => PESO[a.it.severidad] - PESO[b.it.severidad] || a.i - b.i)
    .map((x) => x.it);
}

/** Sólo lo que pide atención: todo menos lo que cumple. */
export function queAtender<T extends { severidad: Severidad }>(items: readonly T[]): T[] {
  return ordenarItems(items.filter((it) => it.severidad !== "bien"));
}

export interface VeredictoCalculado {
  severidad: Severidad;
  frase: string;
}

const cosas = (n: number) => `${n} ${n === 1 ? "cosa" : "cosas"}`;

/** «El tablero cumple» (la frase del panel) sin nada que atender; si no, cuántas cosas hay que
   corregir y cuántas revisar («1 cosa por corregir y 2 por revisar»), con la severidad de la
   más grave. Lo que queda sin evaluar se lista pero no cuenta: si es lo único, cumple lo que se
   revisó (`fraseParcial`, «El tablero cumple lo que revisamos»), sin decir que cumple todo
   (F3b: el calentamiento sin norma no puede tapar la respuesta del panel). */
export function veredictoDe(items: readonly { severidad: Severidad }[], fraseBien: string,
  fraseParcial = "Cumple lo que revisamos"): VeredictoCalculado {
  const atender = queAtender(items);
  if (!atender.length) return { severidad: "bien", frase: fraseBien };
  if (atender.every((it) => it.severidad === "sin_evaluar")) return { severidad: "bien", frase: fraseParcial };
  const cuenta = (s: Severidad) => atender.filter((it) => it.severidad === s).length;
  const f = cuenta("falla"), a = cuenta("aviso");
  const severidad = atender[0].severidad;
  if (f && a) return { severidad, frase: `${cosas(f)} por corregir y ${a} por revisar` };
  if (f) return { severidad, frase: `${cosas(f)} por corregir` };
  return { severidad, frase: `${cosas(a)} por revisar` };
}
