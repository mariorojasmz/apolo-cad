import type * as THREE from "three";
import type { FeatureOut, ZonaOut } from "../types";

/* Zonas de acabado de una pieza (plan seta-de-emergencia, D2): la seta roja sobre el fondo
   amarillo es UNA pieza con varias zonas. El servidor manda `feat.zonas` en índices de
   triángulo; aquí se vuelven `geometry.groups` (en vértices: la geometría del visor es no
   indexada) y la malla lleva un arreglo de materiales, uno por zona, en el orden de las zonas.
   El albedo de cada zona ya viene resuelto (D3: una zona de norma ignora el color asignado).
   Una pieza sin zonas, o con zonas que no cubren su malla, sigue con UN material. */

export interface GrupoZona {
  start: number;
  count: number;
  materialIndex: number;
}

/** Grupos de la geometría para `zonas` sobre una malla de `nTriangulos` triángulos, o null si
 * no hay zonas o no la describen: deben empezar en 0, ser contiguas, no vacías y terminar en
 * el último triángulo (con un arreglo de materiales, un triángulo sin grupo no se dibuja). */
export function gruposDeZonas(zonas: readonly ZonaOut[] | undefined, nTriangulos: number): GrupoZona[] | null {
  if (!zonas || zonas.length === 0) return null;
  let previo = 0;
  for (const z of zonas) {
    if (z.desde !== previo || z.hasta <= z.desde) return null;
    previo = z.hasta;
  }
  if (previo !== nTriangulos) return null;
  return zonas.map((z, i) => ({ start: z.desde * 3, count: (z.hasta - z.desde) * 3, materialIndex: i }));
}

/** Pone en `geom` (no indexada, 3 vértices por triángulo) los grupos de las zonas de `feat`.
 * Devuelve si quedó partida. Sin zonas válidas, la deja sin grupos. */
export function aplicarZonas(geom: THREE.BufferGeometry, zonas: readonly ZonaOut[] | undefined): boolean {
  const n = geom.getAttribute("position").count / 3;
  const grupos = gruposDeZonas(zonas, n);
  geom.clearGroups();
  if (!grupos) return false;
  for (const g of grupos) geom.addGroup(g.start, g.count, g.materialIndex);
  return true;
}

/** ¿La geometría está partida para estas zonas? (un grupo por zona, en el mismo orden). */
export function partidaPara(geom: THREE.BufferGeometry, zonas: readonly ZonaOut[] | undefined): boolean {
  if (!zonas || zonas.length === 0 || geom.groups.length !== zonas.length) return false;
  return zonas.every((z, i) => geom.groups[i].start === z.desde * 3 && geom.groups[i].count === (z.hasta - z.desde) * 3);
}

/** La pieza vista como si fuera sólo esa zona: su acabado y su albedo (para armar su material
 * con la misma fábrica que una pieza entera, texturas procedurales incluidas). */
export function featDeZona(feat: FeatureOut, zona: ZonaOut): FeatureOut {
  return { ...feat, acabado: zona.acabado, albedo: zona.albedo };
}

/** Firma de la apariencia de las zonas (entra en `appearanceSig`). Vacía sin zonas. */
export function firmaZonas(zonas: readonly ZonaOut[] | undefined): string {
  return zonas?.length ? zonas.map((z) => `${z.acabado}:${z.albedo}`).join(",") : "";
}

/** Las zonas de una entrada `same` del delta sobre las de la escena anterior: los rangos son
 * de la geometría que el visor YA tiene (la de `prev`) y la apariencia, la nueva. Si no se
 * corresponden (otra cantidad), mandan las del delta. */
export function zonasDelDelta(prev: readonly ZonaOut[] | undefined, nuevas: readonly ZonaOut[] | undefined): ZonaOut[] | undefined {
  if (!nuevas) return undefined;
  if (!prev || prev.length !== nuevas.length) return [...nuevas];
  return nuevas.map((z, i) => ({ ...z, desde: prev[i].desde, hasta: prev[i].hasta }));
}

/** Los materiales de una malla, sea uno o un arreglo (zonas). */
export function materialesDe(m: THREE.Material | THREE.Material[] | null | undefined): THREE.Material[] {
  if (!m) return [];
  return Array.isArray(m) ? m : [m];
}

/** Libera el material de una malla, sea uno o un arreglo. */
export function liberarMaterial(m: THREE.Material | THREE.Material[] | null | undefined): void {
  for (const x of materialesDe(m)) x.dispose();
}
