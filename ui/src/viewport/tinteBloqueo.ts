import type * as THREE from "three";
import { liberarMaterial } from "./zonas";

/* TINTE de FALLO de guardado: una pieza cuyo guardado FALLÓ (y se reintenta en segundo plano) se
   tiñe de rojizo hasta que persiste, para avisar que ese cambio aún NO está en disco. Durante el
   guardado NORMAL (aunque tarde) NO se tiñe nada — la sincronización es silenciosa. Clona el material
   (no muta compartidos) y se recalcula cada frame → robusto a que el rebuild reemplace la malla.
   Salió de Viewport.tsx sin cambiar la lógica (plan piso-con-sombra, F1). */

/** Devuelve la tarea por frame que aplica y retira el tinte. */
export function crearTinteBloqueo(
  meshes: Map<string, THREE.Mesh>, blockedRef: { readonly current: readonly string[] },
): () => void {
  const tinted = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>(); // malla → material original
  const applyBlockedTint = () => {
    const want = new Set<THREE.Mesh>();
    for (const id of blockedRef.current) { const mm = meshes.get(id) as THREE.Mesh | undefined; if (mm) want.add(mm); }
    for (const [mesh, orig] of tinted) { // restaura las que ya no están bloqueadas
      if (!want.has(mesh)) { liberarMaterial(mesh.material); mesh.material = orig; tinted.delete(mesh); }
    }
    const tenir = (m: THREE.Material) => {
      const clone = (m as THREE.MeshStandardMaterial).clone();
      if (clone.emissive) { clone.emissive.setHex(0x8a2417); clone.emissiveIntensity = 1; }
      return clone;
    };
    for (const mesh of want) { // tinta las nuevas (guardado fallido); con zonas, cada material
      if (tinted.has(mesh) || !mesh.material) continue;
      const orig = mesh.material;
      mesh.material = Array.isArray(orig) ? orig.map(tenir) : tenir(orig);
      tinted.set(mesh, orig);
    }
  };
  return applyBlockedTint;
}
