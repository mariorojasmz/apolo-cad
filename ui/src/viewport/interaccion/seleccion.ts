import * as THREE from "three";
import { useStore } from "../../state/store";
import type { CtxInteraccion } from "./ctx";
import { piezasBajo } from "./alApretar";

/* Selección por clic (y el modo «elegir punto» de los formularios); un clic sobre el ViewCube
   reorienta la vista. Salió de Viewport.tsx sin cambiar la lógica (plan piso-con-sombra, F1). */

export function instalarSeleccion(ctx: CtxInteraccion): () => void {
  const { camera, gizmo, renderer, group, raycaster, viewCube, setViewDir } = ctx;

  let downAt = [0, 0];
  const onDown = (e: MouseEvent) => (downAt = [e.clientX, e.clientY]);
  const onClick = (e: MouseEvent) => {
    if ((gizmo as unknown as { dragging?: boolean }).dragging) return;
    if (Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5) return;
    if (viewCube.handleClick(e, renderer, setViewDir)) return; // clic en el ViewCube
    const rect = renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    const hits = piezasBajo(raycaster, group);
    const store = useStore.getState();

    // modo "elegir punto" (selectores de aristas/caras en formularios)
    if (store.pickRequest) {
      if (hits.length) {
        const p = hits[0].point;
        const cb = store.pickRequest;
        store.requestPick(null);
        cb([Math.round(p.x * 100) / 100, Math.round(p.y * 100) / 100, Math.round(p.z * 100) / 100]);
      }
      return;
    }

    const id = hits.length ? (hits[0].object.userData.featureId as string) : null;
    if (e.ctrlKey || e.metaKey) {
      if (id) store.toggleSelect(id);
    } else {
      store.select(id ? [id] : []);
    }
  };

  renderer.domElement.addEventListener("mousedown", onDown);
  renderer.domElement.addEventListener("click", onClick);
  return () => {
    renderer.domElement.removeEventListener("mousedown", onDown);
    renderer.domElement.removeEventListener("click", onClick);
  };
}
