import * as THREE from "three";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { CatalogItem, FeatureOut, Mesh as MeshPayload } from "../types";
import { buildEdgeMaterial, buildSolidMaterial, isGlass, resolveMaterialParams } from "./materials";

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
  return toCreasedNormals(geometry, CREASE_ANGLE);
}

export function buildMesh(
  feat: FeatureOut,
  shading: Shading,
  planes: THREE.Plane[],
  definitions: Record<string, MeshPayload> | null,
  shared: Map<string, SharedGeom>,
  catalogByRef: Map<string, CatalogItem> | null,
): THREE.Mesh {
  const params = resolveMaterialParams(feat, catalogByRef);
  const glass = isGlass(feat, catalogByRef);
  const material = buildSolidMaterial(feat, params, shading === "wire", planes, glass);
  const lineMaterial = buildEdgeMaterial(planes);

  let mesh: THREE.Mesh;
  let edgesGeom: THREE.EdgesGeometry;

  const defMesh = feat.mesh_key && feat.matrix && definitions ? definitions[feat.mesh_key] : null;
  if (defMesh) {
    /* Instancia: geometría canónica COMPARTIDA entre todas las ocurrencias,
       recentrada una sola vez; la matriz del payload la coloca en el mundo. */
    let entry = shared.get(feat.mesh_key!);
    if (!entry) {
      const geom = geometryFrom(defMesh);
      geom.computeBoundingBox();
      const center = geom.boundingBox!.getCenter(new THREE.Vector3());
      geom.translate(-center.x, -center.y, -center.z);
      entry = { geom, edges: new THREE.EdgesGeometry(geom, 25), center };
      shared.set(feat.mesh_key!, entry);
    }
    mesh = new THREE.Mesh(entry.geom, material);
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
    mesh = new THREE.Mesh(geometry, material);
    mesh.position.copy(center);
    mesh.userData.baseMatrix = new THREE.Matrix4().makeTranslation(center.x, center.y, center.z);
    edgesGeom = new THREE.EdgesGeometry(geometry, 25);
  }

  mesh.castShadow = !glass; // el vidrio translúcido no proyecta sombra opaca
  mesh.receiveShadow = true;
  mesh.userData.featureId = feat.id;
  mesh.userData.p0 = mesh.position.clone();
  mesh.userData.q0 = mesh.quaternion.clone();

  const edges = new THREE.LineSegments(edgesGeom, lineMaterial);
  edges.raycast = () => undefined; // las aristas no capturan clics
  mesh.add(edges);
  return mesh;
}
