import * as THREE from "three";
import type { CatalogItem, FeatureOut } from "../types";

/* Materiales PBR por componente. El material del catálogo (specs.material) llega
   al frontend vía feat.component + el catálogo del store; aquí se traduce a
   parámetros metalness/roughness. El color (albedo) siempre es feat.color, para
   no perder la distinción visual de piezas que da la paleta/color del usuario. */

export interface PbrParams {
  metalness: number;
  roughness: number;
}

export const DEFAULT_PARAMS: PbrParams = { metalness: 0.2, roughness: 0.6 }; // piezas a medida

const MATERIAL_TABLE: Record<string, PbrParams> = {
  aluminio: { metalness: 0.9, roughness: 0.45 },
  "aluminio/acero": { metalness: 0.9, roughness: 0.4 },
  acero: { metalness: 1.0, roughness: 0.3 },
  "acero templado": { metalness: 1.0, roughness: 0.25 },
  "acero al cromo": { metalness: 1.0, roughness: 0.12 },
  "acero 12.9": { metalness: 1.0, roughness: 0.35 },
  "acero zincado": { metalness: 0.85, roughness: 0.5 },
  "acero pintado": { metalness: 0.1, roughness: 0.6 },
  "acero inoxidable": { metalness: 1.0, roughness: 0.2 },
  latón: { metalness: 0.9, roughness: 0.35 },
  "níquel satinado": { metalness: 0.9, roughness: 0.45 },
};

export function resolveMaterialParams(
  feat: FeatureOut,
  catalogByRef: Map<string, CatalogItem> | null,
): PbrParams {
  if (!feat.component || !catalogByRef) return DEFAULT_PARAMS;
  const material = catalogByRef.get(feat.component)?.specs?.material;
  if (typeof material !== "string") return DEFAULT_PARAMS;
  return MATERIAL_TABLE[material.toLowerCase().trim()] ?? DEFAULT_PARAMS;
}

const GLASS_RE = /vidrio|cristal|glass/i;

/** Vidrio: por material de catálogo (specs.material) o por nombre de la feature
   (las piezas a medida de vidrio se llaman "Vidrio ..."). Se renderiza translúcido. */
export function isGlass(feat: FeatureOut, catalogByRef: Map<string, CatalogItem> | null): boolean {
  const mat = feat.component && catalogByRef ? catalogByRef.get(feat.component)?.specs?.material : undefined;
  if (typeof mat === "string" && GLASS_RE.test(mat)) return true;
  return GLASS_RE.test(feat.name);
}

export function buildSolidMaterial(
  feat: FeatureOut,
  params: PbrParams,
  wire: boolean,
  planes: THREE.Plane[],
  glass = false,
): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(feat.color),
    metalness: glass ? 0.0 : params.metalness,
    roughness: glass ? 0.06 : params.roughness,
    envMapIntensity: glass ? 1.4 : 1.0,
    flatShading: false, // las normales por arista (toCreasedNormals) dan el detalle
    wireframe: wire,
    side: THREE.DoubleSide,
    transparent: glass,
    opacity: glass ? 0.3 : 1.0,
    depthWrite: glass ? false : true, // el vidrio no escribe profundidad → se ve lo de detrás
    clippingPlanes: planes.length ? planes : undefined,
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
