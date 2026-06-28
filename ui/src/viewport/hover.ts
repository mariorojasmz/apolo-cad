import * as THREE from "three";

/* Pre-resaltado al pasar el cursor (hover). Raycast sobre group.children; tiñe el
   sólido bajo el cursor con un emisivo SUTIL, distinto y más tenue que la selección
   (que es la fuente de verdad en azul). Nunca tiñe sólidos seleccionados; se desactiva
   durante gizmo-drag/box-select; tolera mallas reconstruidas (comprueba .parent). */

const HOVER_COLOR = 0x6699ff;
const HOVER_INTENSITY = 0.25;

export interface HoverDeps {
  dom: HTMLElement;
  camera: THREE.Camera;
  group: THREE.Group;
  isBusy: () => boolean;
  isSelected: (id: string) => boolean;
}

export function installHover(deps: HoverDeps): () => void {
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let hovered: THREE.Mesh | null = null;

  const restore = (mesh: THREE.Mesh) => {
    const id = mesh.userData.featureId as string;
    if (!mesh.parent || deps.isSelected(id)) return; // borrada o seleccionada → no tocar
    const m = mesh.material as THREE.MeshStandardMaterial;
    m.emissive.set(0x000000);
    m.emissiveIntensity = 0;
  };

  const onMove = (e: PointerEvent) => {
    if (deps.isBusy()) {
      if (hovered) { restore(hovered); hovered = null; }
      return;
    }
    const rect = deps.dom.getBoundingClientRect();
    pointer.set(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, deps.camera);
    const hit = raycaster.intersectObjects(deps.group.children, false)[0];
    const mesh = (hit?.object as THREE.Mesh) ?? null;
    if (mesh === hovered) return;
    if (hovered) restore(hovered);
    hovered = null;
    if (mesh && mesh.userData.featureId && !deps.isSelected(mesh.userData.featureId as string)) {
      const m = mesh.material as THREE.MeshStandardMaterial;
      m.emissive.set(HOVER_COLOR);
      m.emissiveIntensity = HOVER_INTENSITY;
      hovered = mesh;
    }
  };

  const onLeave = () => {
    if (hovered) { restore(hovered); hovered = null; }
  };

  deps.dom.addEventListener("pointermove", onMove);
  deps.dom.addEventListener("pointerleave", onLeave);
  return () => {
    deps.dom.removeEventListener("pointermove", onMove);
    deps.dom.removeEventListener("pointerleave", onLeave);
    if (hovered) restore(hovered);
  };
}
