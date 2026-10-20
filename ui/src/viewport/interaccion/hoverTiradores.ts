import * as THREE from "three";
import type { CtxInteraccion } from "./ctx";

/* Hover de los tiradores del overlay. Salió de Viewport.tsx sin cambiar la lógica (plan
   piso-con-sombra, F1). Devuelve el handler que `pointermove` llama cuando no hay arrastre. */

export function crearHoverTiradores(ctx: CtxInteraccion): (e: PointerEvent) => void {
  const { camera, renderer, raycaster } = ctx;
  // hover de los tiradores: resalta el que está bajo el cursor. Cuadrito (sprite) → tinte azul; flecha de
  // rotación / cono subir-bajar (mesh con material PROPIO) → se aclara, opacidad plena, CRECE y pasa AL
  // FRENTE (renderOrder) → cuando las flechas se solapan en piezas pequeñas se ve cuál se va a clicar.
  let hoveredHandle: THREE.Object3D | null = null;
  const _hoverWhite = new THREE.Color(0xffffff);
  const setHandleHover = (obj: THREE.Object3D, on: boolean) => {
    if ((obj as THREE.Sprite).isSprite) {
      ((obj as THREE.Sprite).material as THREE.SpriteMaterial).color.setHex(on ? 0x4f8bff : obj.userData.baseColor);
      return;
    }
    const m = (obj as THREE.Mesh).material as THREE.MeshBasicMaterial;
    if (on) {
      m.color.setHex(obj.userData.baseColor).lerp(_hoverWhite, 0.55); // conserva el matiz del eje, pero POP
      m.opacity = 1;
      obj.userData.hoverScale = 1.32; // lo aplica el loop de escala (tamaño de pantalla constante)
      obj.renderOrder = 130; // por encima del resto del overlay → al frente aunque se solapen
    } else {
      m.color.setHex(obj.userData.baseColor);
      m.opacity = obj.userData.baseOpacity ?? 1;
      obj.userData.hoverScale = 1;
      obj.renderOrder = obj.userData.baseRenderOrder ?? obj.renderOrder;
    }
  };
  // objeto a RESALTAR para un hit: el sprite es él mismo; la zona de clic ampliada de rotación apunta a su
  // flecha visible (`twin`); el cono es él mismo. null si el hit no es un tirador resaltable.
  const hoverTarget = (o: THREE.Object3D): THREE.Object3D | null => {
    if ((o as THREE.Sprite).isSprite) return o;
    if (o.userData?.kind === "rot") return (o.userData.twin as THREE.Object3D | undefined) ?? o;
    if (o.userData?.kind === "zlift") return o;
    return null;
  };
  const hoverHandles = (e: PointerEvent) => {
    const g = ctx.handles;
    if (!g.visible) {
      if (hoveredHandle) { setHandleHover(hoveredHandle, false); hoveredHandle = null; }
      return;
    }
    const rect = renderer.domElement.getBoundingClientRect();
    raycaster.setFromCamera(
      new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1),
      camera,
    );
    const hit = raycaster.intersectObjects(g.children, false)[0];
    const target = hit ? hoverTarget(hit.object) : null;
    if (target === hoveredHandle) return;
    if (hoveredHandle) setHandleHover(hoveredHandle, false);
    hoveredHandle = target;
    if (target) setHandleHover(target, true);
  };
  return hoverHandles;
}
