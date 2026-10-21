import * as THREE from "three";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { CatalogItem, FeatureOut, Mesh as MeshPayload } from "../types";
import {
  buildEdgeMaterial, buildGuideEdgeMaterial, buildGuideMaterial,
  buildSolidMaterial, isGlass, resolveMaterialParams,
} from "./materials";
import { uvCaja } from "./relieve";
import { aplicarZonas, featDeZona, firmaZonas, liberarMaterial, partidaPara } from "./zonas";

export type Shading = "solid" | "wire";

export interface SharedGeom {
  geom: THREE.BufferGeometry;
  edges: THREE.EdgesGeometry;
  center: THREE.Vector3;
}

const CREASE_ANGLE = THREE.MathUtils.degToRad(35); // <35° se suaviza (curvas), >35° queda nítido (aristas)

export function geometryFrom(payload: MeshPayload): THREE.BufferGeometry {
  let geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(payload.positions, 3));
  geometry.setIndex(payload.indices);
  geometry = geometry.toNonIndexed() as THREE.BufferGeometry;
  // Normales por ángulo de arista: cilindros/rodamientos salen suaves, cajas y
  // perfiles conservan sus cantos vivos (clave para que el PBR no parezca plano).
  const creased = toCreasedNormals(geometry, CREASE_ANGLE);
  uvCaja(creased); // UV en mm para el relieve procedural del acabado
  return creased;
}

/** Material de sólido de una pieza (o de una de sus zonas, vista como pieza: `featDeZona`). */
function solido(feat: FeatureOut, shading: Shading, planes: THREE.Plane[],
  catalogByRef: Map<string, CatalogItem> | null): THREE.Material {
  return buildSolidMaterial(feat, resolveMaterialParams(feat, catalogByRef), shading === "wire",
    planes, isGlass(feat, catalogByRef));
}

/** Materiales (sólido/vidrio/guía) + material de aristas para una feature. Fuente ÚNICA
 * usada por buildMesh (malla nueva) y applyAppearance (reuso de geometría, V6.2b). Con
 * `geom` partida por zonas (seta-de-emergencia D2), el sólido es un arreglo: un material por
 * zona, en el orden de sus grupos; el boceto-guía sigue siendo uno solo. */
function buildMaterials(
  feat: FeatureOut,
  shading: Shading,
  planes: THREE.Plane[],
  catalogByRef: Map<string, CatalogItem> | null,
  geom: THREE.BufferGeometry,
): { material: THREE.Material | THREE.Material[]; lineMaterial: THREE.Material; glass: boolean; guide: boolean } {
  const glass = isGlass(feat, catalogByRef);
  const guide = feat.is_guide === true; // boceto-guía: translúcido ámbar, no es pieza real
  const material = guide
    ? buildGuideMaterial(planes)
    : partidaPara(geom, feat.zonas)
      ? feat.zonas!.map((z) => solido(featDeZona(feat, z), shading, planes, catalogByRef))
      : solido(feat, shading, planes, catalogByRef);
  const lineMaterial = guide ? buildGuideEdgeMaterial(planes) : buildEdgeMaterial(planes);
  return { material, lineMaterial, glass, guide };
}

export function buildMesh(
  feat: FeatureOut,
  shading: Shading,
  planes: THREE.Plane[],
  definitions: Record<string, MeshPayload> | null,
  shared: Map<string, SharedGeom>,
  catalogByRef: Map<string, CatalogItem> | null,
): THREE.Mesh {
  let mesh: THREE.Mesh;
  let edgesGeom: THREE.EdgesGeometry;
  const conMateriales = (geom: THREE.BufferGeometry) => buildMaterials(feat, shading, planes, catalogByRef, geom);
  let mats: ReturnType<typeof conMateriales>;

  const defMesh = feat.mesh_key && feat.matrix && definitions ? definitions[feat.mesh_key] : null;
  if (defMesh) {
    /* Instancia: geometría canónica COMPARTIDA entre todas las ocurrencias,
       recentrada una sola vez; la matriz del payload la coloca en el mundo. Las zonas son de
       la definición (las mismas en todas sus instancias): sus grupos van en la compartida. */
    let entry = shared.get(feat.mesh_key!);
    if (!entry) {
      const geom = geometryFrom(defMesh);
      geom.computeBoundingBox();
      const center = geom.boundingBox!.getCenter(new THREE.Vector3());
      geom.translate(-center.x, -center.y, -center.z);
      entry = { geom, edges: new THREE.EdgesGeometry(geom, 25), center };
      shared.set(feat.mesh_key!, entry);
    }
    if (!entry.geom.groups.length && feat.zonas) aplicarZonas(entry.geom, feat.zonas);
    mats = conMateriales(entry.geom);
    mesh = new THREE.Mesh(entry.geom, mats.material);
    const base = new THREE.Matrix4()
      .fromArray(feat.matrix!)
      .multiply(new THREE.Matrix4().makeTranslation(entry.center.x, entry.center.y, entry.center.z));
    base.decompose(mesh.position, mesh.quaternion, mesh.scale);
    mesh.userData.baseMatrix = base;
    edgesGeom = entry.edges;
  } else {
    /* Pieza única: malla mundial recentrada por su bbox (gizmo y rotación
       sobre el centro, como siempre). */
    const geometry = geometryFrom(feat.mesh!);
    const center = new THREE.Vector3(
      (feat.bbox.min[0] + feat.bbox.max[0]) / 2,
      (feat.bbox.min[1] + feat.bbox.max[1]) / 2,
      (feat.bbox.min[2] + feat.bbox.max[2]) / 2,
    );
    geometry.translate(-center.x, -center.y, -center.z);
    aplicarZonas(geometry, feat.zonas);
    mats = conMateriales(geometry);
    mesh = new THREE.Mesh(geometry, mats.material);
    mesh.position.copy(center);
    mesh.userData.baseMatrix = new THREE.Matrix4().makeTranslation(center.x, center.y, center.z);
    edgesGeom = new THREE.EdgesGeometry(geometry, 25);
  }

  mesh.castShadow = !mats.glass && !mats.guide; // vidrio/boceto translúcidos no proyectan sombra opaca
  mesh.receiveShadow = true;
  mesh.userData.featureId = feat.id;
  mesh.userData.shared = !!defMesh; // instancia → geometría/aristas COMPARTIDAS (no disponer aquí)
  mesh.userData.p0 = mesh.position.clone();
  mesh.userData.q0 = mesh.quaternion.clone();

  const edges = new THREE.LineSegments(edgesGeom, mats.lineMaterial);
  edges.raycast = () => undefined; // las aristas no capturan clics
  mesh.add(edges);
  return mesh;
}

/** Reconstruye SOLO los materiales de una malla existente (V6.2b): cuando la geometría no
 * cambió (rev estable) pero sí un metadato de apariencia (color/material/guía), se reusa la
 * geometría —lo caro— y se cambian los materiales. Dispone los materiales viejos. */
export function applyAppearance(
  mesh: THREE.Mesh,
  feat: FeatureOut,
  shading: Shading,
  planes: THREE.Plane[],
  catalogByRef: Map<string, CatalogItem> | null,
): void {
  const { material, lineMaterial, glass, guide } = buildMaterials(feat, shading, planes, catalogByRef, mesh.geometry);
  liberarMaterial(mesh.material);
  mesh.material = material;
  const edges = mesh.children.find((c) => c instanceof THREE.LineSegments) as THREE.LineSegments | undefined;
  if (edges) {
    (edges.material as THREE.Material).dispose();
    edges.material = lineMaterial;
  }
  mesh.castShadow = !glass && !guide;
}

/** Firma de APARIENCIA de una feature (barata): decide si applyAppearance debe correr para
 * una malla de geometría estable. NO incluye la geometría (esa la cubre `rev`). */
export function appearanceSig(feat: FeatureOut): string {
  // albedo + acabado (tabla D5: metalness/roughness/relieve/vidrio), color y name (respaldo
  // sin acabado), is_guide (translúcido ámbar) y la apariencia de cada zona — todo lo que
  // buildMaterials/isGlass leen. Sin zonas, la firma de siempre.
  const sig = `${feat.albedo ?? ""}|${feat.acabado ?? ""}|${feat.color}|${feat.name}|${feat.is_guide ? 1 : 0}`;
  const zonas = firmaZonas(feat.zonas);
  return zonas ? `${sig}|${zonas}` : sig;
}

/** Dispone una malla y sus aristas. NO toca geometría/aristas COMPARTIDAS de instancias
 * (esas las gestiona el pool `shared`); sí dispone siempre los materiales (por-malla). */
export function disposeMesh(mesh: THREE.Mesh): void {
  liberarMaterial(mesh.material);
  const edges = mesh.children.find((c) => c instanceof THREE.LineSegments) as THREE.LineSegments | undefined;
  if (edges) (edges.material as THREE.Material).dispose();
  if (!mesh.userData.shared) {
    mesh.geometry.dispose();
    (edges?.geometry as THREE.BufferGeometry | undefined)?.dispose();
  }
}

/** Dispone una entrada del pool de geometrías compartidas (cuando ninguna malla la usa). */
export function disposeSharedGeom(entry: SharedGeom): void {
  entry.geom.dispose();
  entry.edges.dispose();
}
