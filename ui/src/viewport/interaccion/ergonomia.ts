import * as THREE from "three";
import { useStore } from "../../state/store";
import { areaLibreDe } from "../areaLibre";
import { crearAtenuador, EVENTO_RESTAURAR } from "../atenuar";
import { cajaConContexto, cajaDe, idsDelEncuadre } from "../camara";
import { cajaConApertura, direccionFrente, elegirVista, poseEnArea } from "../encuadreLibre";
import { installGltfExport } from "../exportGltf";
import { opcionesDelEncuadre } from "../pedirEncuadre";
import { crearVueloCamara } from "../vuelo";
import type { CtxInteraccion } from "./ctx";

/* Ergonomía: menú contextual suprimido (el derecho orbita), doble clic enfoca, encuadre por el
   evento `apolo:fit` y exportación glTF. Salió de Viewport.tsx sin cambiar la lógica (plan
   piso-con-sombra, F1). `apolo:fit` con `animar` vuela y con `seleccionar` deja las piezas con
   el contorno de selección (plan V8.5, F3b-0; `pedirEncuadre.ts`); sin ellos, salta como antes.
   Todo encuadre centra en el área que se ve (sin el panel lateral), `frente` mira la cara de una
   pieza y `despejar` esquiva o atenúa lo que tapa (plan visor-para-evaluar D13–D15,
   `encuadreLibre.ts`). Lo atenuado vuelve con el próximo encuadre o con `EVENTO_RESTAURAR`. */

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
  const atenuador = crearAtenuador();
  const restaurar = () => atenuador.restaurar();
  // hook de depuración (como `meshIds`): lo atenuado y dónde quedó la cámara, sin screenshot
  const hook = (window as unknown as { __apolo?: Record<string, unknown> }).__apolo;
  if (hook) {
    hook.atenuadas = () => atenuador.ids();
    hook.camara = () => ({ posicion: camera.position.toArray(), objetivo: controls.target.toArray() });
  }
  const onFitEvent = (ev: Event) => { // detail.id (una pieza) o detail.ids (varias, «Ver» del aviso)
    const detail = (ev as CustomEvent).detail;
    const ids = idsDelEncuadre(detail);
    const { animar, seleccionar, puntos, frente, despejar } = opcionesDelEncuadre(detail);
    atenuador.restaurar();
    let box = cajaDe(ctx.meshes, ids);
    for (const [x, y, z] of puntos) box = (box ?? new THREE.Box3()).expandByPoint(new THREE.Vector3(x, y, z));
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
    const area = areaLibreDe(renderer.domElement);
    const modelo = new THREE.Box3().setFromObject(group);
    let dir = camera.position.clone().sub(controls.target);
    let caja: THREE.Box3 | null = null;
    const mFrente = frente ? ctx.meshes.get(frente) : undefined;
    if (box && mFrente) { // de frente a esa cara, con lo que la pieza abre hacia la cámara
      const d = direccionFrente(mFrente, box, camera.position);
      if (d) {
        dir = d;
        caja = cajaConApertura(box, new THREE.Box3().setFromObject(mFrente), d);
      }
    }
    caja ??= box ? cajaConContexto(box, modelo) : cajaDe(ctx.meshes, useStore.getState().selection) ?? modelo;
    let destino = poseEnArea(caja, dir, camera, area);
    if (despejar && box) {
      // no tapan lo encuadrado ni las piezas de su mismo comando (los mandos de la puerta, la
      // placa del tablero): son parte de lo que se mira
      const feats = useStore.getState().scene?.features ?? [];
      const comandos = new Set(feats.filter((f) => ids.includes(f.id)).map((f) => f.command_id));
      const propias = new Set([...ids, ...(frente ? [frente] : []),
        ...feats.filter((f) => comandos.has(f.command_id)).map((f) => f.id)]);
      const vista = elegirVista(caja, box, dir, camera, area, group.children, propias);
      if (vista) {
        destino = vista.pose;
        atenuador.atenuar(vista.atenuar.map((id) => ctx.meshes.get(id)).filter((m): m is THREE.Mesh => !!m));
      }
    }
    if (destino) vuelo.volar(destino);
  };
  renderer.domElement.addEventListener("contextmenu", onContext);
  renderer.domElement.addEventListener("dblclick", onDblClick);
  window.addEventListener("apolo:fit", onFitEvent as EventListener);
  window.addEventListener(EVENTO_RESTAURAR, restaurar);
  const disposeGltfExport = installGltfExport(
    group, () => useStore.getState().scene?.document.name ?? "modelo",
  );
  return () => {
    renderer.domElement.removeEventListener("contextmenu", onContext);
    renderer.domElement.removeEventListener("dblclick", onDblClick);
    window.removeEventListener("apolo:fit", onFitEvent as EventListener);
    window.removeEventListener(EVENTO_RESTAURAR, restaurar);
    atenuador.restaurar();
    vuelo.dispose();
    disposeGltfExport();
  };
}
