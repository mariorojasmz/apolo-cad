/* Lógica pura de la ficha de pieza del visor (plan modo-visor, D7): cómo se escriben las
   medidas, el peso y el material, y la caché de la masa. Sin React, para probarla con vitest. */

/** Lo que se muestra mientras un dato carga o si no se pudo leer. */
export const SIN_DATO = "—";

export interface Caja {
  min: number[];
  max: number[];
}

/** 4000 → «4000», 101.60000001 → «101.6»: un decimal como mucho y sin ceros de relleno. */
const mm = (v: number): string => String(Number(v.toFixed(1)) || 0);

/** Medidas de la caja envolvente, X × Y × Z: «4000 × 101.6 × 50.8 mm». */
export function formatearMedidas(b: Caja): string {
  const d = [0, 1, 2].map((i) => (b.max[i] ?? NaN) - (b.min[i] ?? NaN));
  if (d.some((v) => !Number.isFinite(v) || v < 0)) return SIN_DATO;
  return `${d.map(mm).join(" × ")} mm`;
}

/** Peso con los decimales que dicen algo: 123.4 kg · 2.59 kg · 0.012 kg. */
export function formatearPeso(kg: number): string {
  if (!Number.isFinite(kg) || kg < 0) return SIN_DATO;
  if (kg === 0) return "0 kg";
  const decimales = kg >= 100 ? 1 : kg >= 1 ? 2 : 3;
  return `${kg.toFixed(decimales)} kg`;
}

/* Las claves de material del servidor van sin tildes ni mayúsculas (`laton`, `pvc`). */
const ROTULO_MATERIAL: Record<string, string> = {
  laton: "Latón",
  carton: "Cartón",
  pvc: "PVC",
};

/** «acero inoxidable» → «Acero inoxidable»; «laton» → «Latón». */
export function nombreMaterial(m: string): string {
  const clave = m.trim().toLowerCase();
  if (!clave) return SIN_DATO;
  return ROTULO_MATERIAL[clave] ?? clave.charAt(0).toUpperCase() + clave.slice(1);
}

/** Caché de la masa por pieza, con clave id + `rev` (la revisión de su geometría). El material
   es metadato del documento: cambiarlo (p. ej. el agente con `set_material`) no sube el `rev`.
   Por eso la caché vale para UNA versión del documento (`doc`, la escena vigente) y se vacía
   cuando llega otra: dentro de la misma, volver a elegir una pieza no repite el fetch. */
export class CacheMasa<T> {
  private doc: unknown = undefined;
  private datos = new Map<string, T>();

  private versionDe(doc: unknown): Map<string, T> {
    if (doc !== this.doc) {
      this.doc = doc;
      this.datos = new Map();
    }
    return this.datos;
  }

  leer(doc: unknown, id: string, rev: number): T | undefined {
    return this.versionDe(doc).get(`${id}@${rev}`);
  }

  /** Guarda para la versión que se leyó por última vez; una respuesta que llega tarde, de una
     versión vieja, se descarta en vez de vaciar la vigente. */
  guardar(doc: unknown, id: string, rev: number, valor: T): void {
    if (doc !== this.doc) return;
    this.datos.set(`${id}@${rev}`, valor);
  }
}
