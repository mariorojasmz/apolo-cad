import { cifra } from "./cifra";

/* Lo puro del `<Deslizador>`: cuánto de la pista va lleno y cómo se lee el valor. */

/** Porcentaje de la pista que va lleno (0–100), acotado; con un rango vacío, 0. */
export function avance(valor: number, min: number, max: number): number {
  if (!(max > min) || !Number.isFinite(valor)) return 0;
  return Math.min(100, Math.max(0, ((valor - min) / (max - min)) * 100));
}

/** Los decimales que pide el paso: 1 → 0, 0,1 → 1, 0,25 → 2. */
export function decimalesDelPaso(paso: number): number {
  if (!(paso > 0) || paso >= 1) return 0;
  const s = String(paso);
  const i = s.indexOf(".");
  return i < 0 ? 0 : Math.min(4, s.length - i - 1);
}

/** Lo que se lee a la vista y en el lector (`aria-valuetext`): «90°», «45,5 mm», «64 %». */
export function textoDeslizador(valor: number, paso: number, unidad = "", decimales?: number): string {
  return cifra(valor, decimales ?? decimalesDelPaso(paso), unidad);
}
