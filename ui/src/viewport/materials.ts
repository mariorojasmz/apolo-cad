import * as THREE from "three";
import type { CatalogItem, FeatureOut } from "../types";
import { ACABADOS, acabadoDe, albedoDe, claveAcabado, type Acabado } from "./acabados";
import { texturaRelieve } from "./relieve";

/* Materiales PBR de las piezas: los parámetros salen de la tabla de acabados D5
   (`acabados.ts`, la misma que usa el render VTK), según el acabado que el servidor resolvió
   para cada pieza (material, rol, catálogo). El color es el albedo que manda el servidor: el
   asignado por el usuario, el propio del acabado (caucho, galvanizado…) o el de la paleta en
   lo pintado, que es lo que distingue una pieza de otra. */

export interface PbrParams {
  metalness: number;
  roughness: number;
}

/** Parámetros PBR del acabado de la pieza. `catalogByRef` queda por compatibilidad: el
 * material de catálogo ya viene resuelto en `feat.acabado`. */
export function resolveMaterialParams(
  feat: FeatureOut,
  _catalogByRef?: Map<string, CatalogItem> | null,
): PbrParams {
  const ac = acabadoDe(feat);
  return { metalness: ac.metalness, roughness: ac.roughness };
}

const GLASS_RE = /vidrio|cristal|glass/i;

/** Vidrio: el acabado `vidrio` (material de la pieza, de su ficha de catálogo o de su nombre).
 * Sin acabado del servidor, por el nombre. Se renderiza translúcido. */
export function isGlass(feat: FeatureOut, _catalogByRef?: Map<string, CatalogItem> | null): boolean {
  if (feat.acabado) return claveAcabado(feat) === "vidrio";
  return GLASS_RE.test(feat.name);
}

export function buildSolidMaterial(
  feat: FeatureOut,
  params: PbrParams,
  wire: boolean,
  planes: THREE.Plane[],
  glass = false,
): THREE.MeshStandardMaterial {
  const ac: Acabado = acabadoDe(feat);
  const bump = !glass && !wire && ac.relieve ? texturaRelieve(ac.relieve) : null;
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(albedoDe(feat)),
    metalness: glass ? 0.0 : params.metalness,
    roughness: glass ? 0.06 : params.roughness,
    envMapIntensity: glass ? 1.4 : 1.0,
    flatShading: false, // las normales por arista (toCreasedNormals) dan el detalle
    wireframe: wire,
    side: THREE.DoubleSide,
    transparent: glass,
    opacity: glass ? ACABADOS.vidrio.opacidad : 1.0,
    depthWrite: glass ? false : true, // el vidrio no escribe profundidad → se ve lo de detrás
    clippingPlanes: planes.length ? planes : undefined,
    bumpMap: bump,
    bumpScale: bump && ac.relieve ? ac.relieve.intensidad : 1,
  });
}

export function buildEdgeMaterial(planes: THREE.Plane[]): THREE.LineBasicMaterial {
  return new THREE.LineBasicMaterial({
    color: 0x12141a,
    transparent: true,
    opacity: 0.5,
    clippingPlanes: planes.length ? planes : undefined,
  });
}

export const GUIDE_COLOR = 0xffab40; // ámbar: boceto-guía (blockout), geometría de intención

/* Boceto-guía: relleno translúcido ámbar + aristas marcadas. Se distingue al instante de
   una pieza real; no escribe profundidad (se ve lo de detrás), como el vidrio. */
export function buildGuideMaterial(planes: THREE.Plane[]): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(GUIDE_COLOR),
    metalness: 0.0,
    roughness: 0.9,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.28,
    depthWrite: false,
    clippingPlanes: planes.length ? planes : undefined,
  });
}

export function buildGuideEdgeMaterial(planes: THREE.Plane[]): THREE.LineBasicMaterial {
  return new THREE.LineBasicMaterial({
    color: GUIDE_COLOR,
    transparent: true,
    opacity: 0.95,
    clippingPlanes: planes.length ? planes : undefined,
  });
}
