import type { MutableRefObject } from "react";
import * as THREE from "three";
import type { CatalogItem, FeatureOut, Mesh as MeshPayload } from "../types";
import {
  applyAppearance, appearanceSig, buildMesh, disposeMesh, disposeSharedGeom,
  type Shading, type SharedGeom,
} from "./meshes";
import type { VistaCtx } from "./interaccion/ctx";

/* Reconstruir mallas con diff persistente (V6.2b). En vez de tirar y reconstruir TODAS las mallas
   en cada cambio de escena, se diffea por fid usando `rev` (revisión de geometría del server):
   sólo la pieza cuyo shape cambió se reconstruye; las demás conservan su malla three.js (lo caro
   es teselar + aristas). Un metadato de apariencia (color/material/guía) rehace sólo el material.
   Shading/sección/catálogo cambian el material/recorte de TODAS → rebuild total. Salió de
   Viewport.tsx sin cambiar la lógica (plan piso-con-sombra, F1). */

export interface MallaConstruida { rev: number; mesh: THREE.Mesh; app: string; key: string | null }

/** Estado del diff entre pasadas: lo construido por fid (rev + firma de apariencia), el pool de
   geometrías de instancia, la clave de invalidación TOTAL y el contador de builds (E2E). */
export interface RefsMallas {
  builtRef: MutableRefObject<Map<string, MallaConstruida>>;
  sharedRef: MutableRefObject<Map<string, SharedGeom>>;
  buildKeyRef: MutableRefObject<string>;
  buildCountRef: MutableRefObject<number>;
}

export function sincronizarMallas(
  ctx: Pick<VistaCtx, "group" | "meshes">,
  { builtRef, sharedRef, buildKeyRef, buildCountRef }: RefsMallas,
  features: FeatureOut[],
  definitions: Record<string, MeshPayload> | null,
  shading: Shading,
  planes: THREE.Plane[],
  catalog: CatalogItem[],
): void {
  const catalogByRef = new Map(catalog.map((c) => [c.ref, c]));
  const built = builtRef.current;
  const shared = sharedRef.current;

  // Invalidación TOTAL: los planos de sección dependen del bbox del modelo (cambian al
  // editar con sección activa) → su firma entra en la clave; shading/catálogo también.
  const planeSig = planes
    .map((p) => `${p.normal.x},${p.normal.y},${p.normal.z},${p.constant.toFixed(2)}`)
    .join(";");
  const buildKey = `${shading}|${planeSig}|${catalog.length}`;
  if (buildKey !== buildKeyRef.current) {
    for (const e of built.values()) disposeMesh(e.mesh);
    ctx.group.clear();
    ctx.meshes.clear();
    built.clear();
    for (const g of shared.values()) disposeSharedGeom(g);
    shared.clear();
    buildKeyRef.current = buildKey;
  }

  // 1) (re)construir lo nuevo o de rev distinto; actualizar apariencia en sitio el resto
  const desired = new Set<string>();
  for (const feat of features) {
    if (!feat.visible) continue;
    desired.add(feat.id);
    const rev = feat.rev ?? 0;
    const app = appearanceSig(feat);
    const prev = built.get(feat.id);
    if (prev && prev.rev === rev) {
      if (prev.app !== app) {
        applyAppearance(prev.mesh, feat, shading, planes, catalogByRef);
        prev.app = app;
      }
      continue; // geometría REUSADA (lo caro no se repite)
    }
    if (prev) { ctx.group.remove(prev.mesh); disposeMesh(prev.mesh); }
    const mesh = buildMesh(feat, shading, planes, definitions, shared, catalogByRef);
    buildCountRef.current++;
    ctx.meshes.set(feat.id, mesh);
    ctx.group.add(mesh);
    built.set(feat.id, { rev, mesh, app, key: feat.mesh_key });
  }
  // 2) quitar mallas de fids desaparecidos o que se ocultaron
  for (const [fid, e] of [...built]) {
    if (!desired.has(fid)) {
      ctx.group.remove(e.mesh);
      disposeMesh(e.mesh);
      built.delete(fid);
      ctx.meshes.delete(fid);
    }
  }
  // 3) podar geometrías de instancia que ya ninguna malla usa
  const usedKeys = new Set<string>();
  for (const e of built.values()) if (e.key) usedKeys.add(e.key);
  for (const [k, g] of [...shared]) {
    if (!usedKeys.has(k)) { disposeSharedGeom(g); shared.delete(k); }
  }
}
