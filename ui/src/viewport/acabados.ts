import tabla from "./acabados.json";
import type { FeatureOut } from "../types";

/* Tabla de acabados D5 (docs/plans/visor-realista.md): cómo se ve cada material. La fuente
   ÚNICA es core/apolo/library/apariencia.py; acabados.json es su copia generada
   (scripts/acabados_ui.py) y tests/test_apariencia.py falla si difieren. El servidor resuelve
   el acabado y el albedo de cada pieza (material, rol, catálogo, color asignado) y los manda en
   la escena (`feat.acabado`, `feat.albedo`): aquí sólo se leen sus parámetros PBR. El render
   VTK del kernel lee la MISMA tabla, así el visor y las fotos/videos se ven igual. */

export interface Relieve {
  tipo: string;
  escala_mm: number;
  intensidad: number;
}

/** Variación procedural de color y brillo (video-realista D2): la genera `textura.ts`. */
export interface Textura {
  tipo: string;
  escala_mm: number;
  variacion_color: number; // 0..1 alrededor del albedo (el promedio no cambia)
  variacion_rugosidad: number; // 0..1 alrededor de la rugosidad de la tabla
  anisotropia: number; // 0..1, sólo el cepillado: reflejo estirado a lo largo de las rayas
}

export interface Acabado {
  nombre: string;
  color: string | null; // albedo propio; null = el color de la pieza (pintura)
  metalness: number;
  roughness: number;
  opacidad: number;
  relieve: Relieve | null;
  pintable: boolean; // el color asignado define el albedo; en un metal manda `color` (lo resuelve el servidor)
  textura: Textura | null;
}

export const ACABADOS: Record<string, Acabado> = tabla.acabados as Record<string, Acabado>;
export const ACABADO_POR_DEFECTO: string = tabla.por_defecto;
export const TIPOS_RELIEVE: readonly string[] = tabla.tipos_relieve;
export const TIPOS_TEXTURA: readonly string[] = tabla.tipos_textura;
/** El acabado de cada color de ficha (`specs.color`, sin tildes y en minúscula) de un mando o
 * piloto: copia de `apariencia.ACABADO_DE_COLOR` (pedidos-de-extensiones-ii, D-a). */
export const ACABADO_DE_COLOR: Readonly<Record<string, string>> = tabla.acabado_de_color;

/** La clave del acabado de un color de ficha («Ámbar», «verde »), o null si la tabla no lo
 * tiene: la misma normalización que el loader (sin tildes, minúscula, sin espacios a los lados). */
export function acabadoDeColor(nombre: string | null | undefined): string | null {
  if (!nombre) return null;
  const k = nombre.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().trim();
  const clave = ACABADO_DE_COLOR[k];
  return clave && clave in ACABADOS ? clave : null;
}

/** Clave del acabado de la pieza: la que manda el servidor o, si no llega o no se conoce,
 * el de por defecto (acero pintado). */
export function claveAcabado(feat: Pick<FeatureOut, "acabado">): string {
  return feat.acabado && feat.acabado in ACABADOS ? feat.acabado : ACABADO_POR_DEFECTO;
}

export function acabadoDe(feat: Pick<FeatureOut, "acabado">): Acabado {
  return ACABADOS[claveAcabado(feat)];
}

/** Color con que se pinta la pieza: el albedo resuelto por el servidor (el asignado sólo en un
 * acabado pintable); sin él, el color de la pieza (asignado o de paleta). Es el que muestran
 * también las muestras de color. */
export function albedoDe(feat: Pick<FeatureOut, "albedo" | "color">): string {
  return feat.albedo ?? feat.color;
}
