import * as THREE from "three";
import { useStore } from "../../state/store";
import { cajaConContexto, cajaDe, destinoEncuadre, idsDelEncuadre } from "../camara";
import { installGltfExport } from "../exportGltf";
import { opcionesDelEncuadre } from "../pedirEncuadre";
import { crearVueloCamara } from "../vuelo";
import type { CtxInteraccion } from "./ctx";

/* Ergonomía: menú contextual suprimido (el derecho orbita), doble clic enfoca, encuadre por el
   evento `apolo:fit` y exportación glTF. Salió de Viewport.tsx sin cambiar la lógica (plan
   piso-con-sombra, F1). `apolo:fit` con `animar` vuela y con `seleccionar` deja las piezas con
   el contorno de selección (plan V8.5, F3b-0; `pedirEncuadre.ts`); sin ellos, salta como antes. */

export function instalarErgonomia(ctx: CtxInteraccion): () => void {
  const { camera, controls, renderer, group, raycaster, frameBox, fitTo } = ctx;
  const vuelo = crearVueloCamara(camera, controls);
  ctx.antesDeComponer(vuelo.tick);
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
    vuelo.cancelar();
    useStore.getState().select([id]);
    const mesh = ctx.meshes.get(id);
    if (mesh) frameBox(new THREE.Box3().setFromObject(mesh));
  };
  const onFitEvent = (ev: Event) => { // detail.id (una pieza) o detail.ids (varias, «Ver» del aviso)
    const detail = (ev as CustomEvent).detail;
    const ids = idsDelEncuadre(detail);
    const { animar, seleccionar } = opcionesDelEncuadre(detail);
    const box = cajaDe(ctx.meshes, ids);
    if (seleccionar) {
      const aLaVista = ids.filter((id) => ctx.meshes.has(id));
      if (aLaVista.length) useStore.getState().select(aLaVista);
    }
    if (!animar) {
      vuelo.cancelar();
      if (box) frameBox(box);
      else fitTo();
      return;
    }
    // las piezas (con contexto: una pieza chica no llena la vista), si no la selección, si no el modelo
    const modelo = new THREE.Box3().setFromObject(group);
    const caja = box ? cajaConContexto(box, modelo) : cajaDe(ctx.meshes, useStore.getState().selection) ?? modelo;
    const destino = destinoEncuadre(camera.position, controls.target, caja);
    if (destino) vuelo.volar(destino);
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
    vuelo.dispose();
    disposeGltfExport();
  };
}
