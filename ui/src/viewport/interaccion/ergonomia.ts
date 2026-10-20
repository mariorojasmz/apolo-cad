import * as THREE from "three";
import { useStore } from "../../state/store";
import { cajaDe, idsDelEncuadre } from "../camara";
import { installGltfExport } from "../exportGltf";
import type { CtxInteraccion } from "./ctx";

/* Ergonomía: menú contextual suprimido (el derecho orbita), doble clic enfoca, encuadre por el
   evento `apolo:fit` y exportación glTF. Salió de Viewport.tsx sin cambiar la lógica (plan
   piso-con-sombra, F1). */

export function instalarErgonomia(ctx: CtxInteraccion): () => void {
  const { camera, renderer, group, raycaster, frameBox, fitTo } = ctx;
  const pickAt = (e: MouseEvent): string | null => {
    const rect = renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(group.children, false);
    return hits.length ? (hits[0].object.userData.featureId as string) : null;
  };
  // El botón derecho ORBITA (mapeo TinkerCad) → solo suprimimos el menú del navegador;
  // las acciones sobre la selección viven en la barra contextual (aparece al seleccionar).
  const onContext = (e: MouseEvent) => e.preventDefault();
  const onDblClick = (e: MouseEvent) => {
    const id = pickAt(e);
    if (!id) return;
    useStore.getState().select([id]);
    const mesh = ctx.meshes.get(id);
    if (mesh) frameBox(new THREE.Box3().setFromObject(mesh));
  };
  const onFitEvent = (ev: Event) => { // detail.id (una pieza) o detail.ids (varias, «Ver» del aviso)
    const box = cajaDe(ctx.meshes, idsDelEncuadre((ev as CustomEvent).detail));
    if (box) frameBox(box);
    else fitTo();
  };
  renderer.domElement.addEventListener("contextmenu", onContext);
  renderer.domElement.addEventListener("dblclick", onDblClick);
  window.addEventListener("apolo:fit", onFitEvent as EventListener);
  const disposeGltfExport = installGltfExport(
    group, () => useStore.getState().scene?.document.name ?? "modelo",
  );
  return () => {
    renderer.domElement.removeEventListener("contextmenu", onContext);
    renderer.domElement.removeEventListener("dblclick", onDblClick);
    window.removeEventListener("apolo:fit", onFitEvent as EventListener);
    disposeGltfExport();
  };
}
