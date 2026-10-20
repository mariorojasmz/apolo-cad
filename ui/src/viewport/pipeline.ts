import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { OutlinePass } from "three/examples/jsm/postprocessing/OutlinePass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import type { Pass } from "three/examples/jsm/postprocessing/Pass.js";
import { BACKGROUND_CSS, createGround, createLights, createRenderer } from "./scene-setup";
import { crearEntorno } from "./environment";
import { useCalidad, type Calidad } from "./calidad";
import { crearCalidadVista, type CalidadVista } from "./calidadVista";
import { createViewCube, type ViewCube } from "./viewcube";
import { crearDestello } from "./destello";
import { ajustarRecorte, crearEncuadreDe } from "./recorte";

/* El pipeline de render del visor: renderer, escena, cámara, controles, luces, suelo, IBL,
   ViewCube, gizmo, el EffectComposer con sus passes, el `resize` y el bucle de render. Salió de
   Viewport.tsx sin cambiar la lógica (plan piso-con-sombra, F1).

   Bucle por frame: `controls.update()` → las tareas de `antesDeComponer` en el orden en que se
   registraron → contorno de selección y destello → `composer.render()` → ViewCube encima. Un
   pase que no es de post-proceso (la sombra de contacto, D2) se engancha ahí: corre después de
   que los animadores movieron las mallas y antes de componer el frame.

   Calidad (video-realista D1, `calidad.ts`): «alta» = estudio procedural como IBL + GTAO + SMAA
   sin MSAA (`calidadVista.ts`); «normal» = RoomEnvironment + MSAA ×4, el visor de antes. El
   pipeline sigue a la store `useCalidad` y la cambia en caliente (sin rearmar nada).

   Grabación (video-realista D3, `grabacion/modo.ts`): `modoGrabacion` fija el tamaño del render,
   para el bucle y deja de dibujar el ViewCube y de mover los controles; el modo grabación llama
   `prepararCuadro(ms)` + `componer()` con su reloj virtual. Por eso las tareas reciben `ahora`:
   ninguna lee el reloj real por su cuenta. */

/** Tarea por cuadro; `ahora` = el reloj del cuadro en ms (el real, o el virtual al grabar). */
export type TareaCuadro = (ahora: number) => void;

export interface Pipeline {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  gizmo: TransformControls;
  group: THREE.Group;
  meshes: Map<string, THREE.Mesh>;
  dir: THREE.DirectionalLight;
  ground: THREE.Mesh;
  viewCube: ViewCube;
  composer: EffectComposer;
  /** Pases que el modo grabación apaga o reemplaza. */
  pases: { render: RenderPass; contorno: OutlinePass; destello: Pass };
  /** Ayudas de la interfaz (grilla, ejes, gizmo): no salen en un video. */
  ayudantes: THREE.Object3D[];
  /** Los pases y el interruptor de la calidad del visor. */
  calidad: CalidadVista;
  /** Aplica una calidad sin tocar la elección guardada de la persona (la grabación fuerza «alta»). */
  aplicarCalidad: (c: Calidad) => void;
  /** Registra una tarea por frame que corre ANTES de componer, en orden de registro. */
  antesDeComponer: (tarea: TareaCuadro) => void;
  /** Controles, tareas y ajustes del cuadro con el reloj `ahora` (ms), sin dibujar. */
  prepararCuadro: (ahora: number) => void;
  /** Dibuja el cuadro (y el ViewCube encima, salvo al grabar). */
  componer: () => void;
  /** Tamaño fijo y sin bucle (grabación) o `null` para volver al visor. */
  modoGrabacion: (tam: { ancho: number; alto: number } | null) => void;
  /** Arranca el bucle (el primer frame se dibuja YA, sincrónico). */
  arrancar: () => void;
  /** Para el bucle y el ResizeObserver (primer paso de la limpieza). */
  detener: () => void;
  /** Libera gizmo, IBL, ViewCube, passes, composer y renderer y quita el canvas (último paso). */
  dispose: () => void;
}

/** `seleccion` = ids seleccionados AHORA (se lee cada frame: robusto a reconstrucciones). */
export function crearPipeline(mount: HTMLDivElement, seleccion: () => readonly string[]): Pipeline {
  const renderer = createRenderer();
  mount.style.background = BACKGROUND_CSS; // el fondo lo pinta el div (canvas transparente) → sin tone-mapping
  mount.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 1, 100000);
  camera.up.set(0, 0, 1);
  camera.position.set(900, -900, 700);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.zoomToCursor = true; // zoom hacia el cursor (estilo CAD)
  // Mapeo TinkerCad: DERECHO=orbitar, MEDIO=pan, rueda=zoom. El IZQUIERDO queda libre para
  // seleccionar/agarrar/mover (lo maneja el viewport); LEFT:null desactiva su orbit nativo.
  controls.mouseButtons = { LEFT: null, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.ROTATE } as unknown as typeof controls.mouseButtons;

  const { dir } = createLights(scene);
  const ground = createGround(scene);
  const entorno = crearEntorno(renderer, scene);
  const viewCube = createViewCube();

  // líneas CLARAS semitransparentes: se leen igual de suaves sobre el fondo y sobre el piso de
  // estudio (con líneas oscuras, el disco claro dejaba un parche de grilla negra)
  const grid = new THREE.GridHelper(4000, 80, 0xb4bccb, 0xb4bccb);
  grid.rotation.x = Math.PI / 2;
  const gridMat = grid.material as THREE.LineBasicMaterial;
  gridMat.transparent = true;
  gridMat.opacity = 0.06;
  gridMat.depthWrite = false;
  scene.add(grid);
  const ejes = new THREE.AxesHelper(220);
  scene.add(ejes);

  const group = new THREE.Group();
  scene.add(group);

  const gizmo = new TransformControls(camera, renderer.domElement);
  gizmo.setSpace("world");
  const gizmoObj = (gizmo as unknown as { getHelper?: () => THREE.Object3D }).getHelper?.() ??
    (gizmo as unknown as THREE.Object3D);
  scene.add(gizmoObj);

  const meshes = new Map<string, THREE.Mesh>();

  // Post-proceso: contorno de SELECCIÓN (silueta, estilo TinkerCad). EffectComposer con un
  // render-target MULTIMUESTREADO + HalfFloat → conserva el antialias (MSAA) y el tone-mapping
  // HDR de la escena PBR intactos (RenderPass en lineal → OutputPass aplica ACES+sRGB al final).
  // OutlinePass resalta SOLO el contorno proyectado de la pieza seleccionada (no las aristas
  // interiores que ve la cámara): remplaza el antiguo tinte emissive de selección.
  const composerRT = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 });
  const composer = new EffectComposer(renderer, composerRT);
  composer.setPixelRatio(window.devicePixelRatio);
  const renderPass = new RenderPass(scene, camera);
  composer.addPass(renderPass);
  const calidad = crearCalidadVista(scene, camera, group, composer);
  composer.addPass(calidad.gtao); // oclusión ambiental, sólo en «alta»
  const outlinePass = new OutlinePass(new THREE.Vector2(1, 1), scene, camera);
  outlinePass.edgeStrength = 4.0;
  outlinePass.edgeGlow = 0.0;      // línea nítida, sin halo
  outlinePass.edgeThickness = 1.0;
  outlinePass.pulsePeriod = 0;     // sin parpadeo
  outlinePass.visibleEdgeColor.set(0x2ec5ff); // contorno visible: cian-azul (TinkerCad)
  outlinePass.hiddenEdgeColor.set(0x14506e);  // parte del contorno tapada por otra pieza: tenue
  composer.addPass(outlinePass);
  const destello = crearDestello(scene, camera); // contorno verde de lo que cambió el agente (modo-visor D8)
  composer.addPass(destello.pass);
  composer.addPass(new OutputPass());
  composer.addPass(calidad.smaa); // antialias sobre sRGB, sólo en «alta»
  const aplicarCalidad = (c: Calidad) => {
    calidad.fijar(c);
    entorno.fijar(c);
  };
  const gl = renderer.getContext();
  const info = gl.getExtension("WEBGL_debug_renderer_info");
  useCalidad.getState().sugerirPorGpu(info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : null);
  aplicarCalidad(useCalidad.getState().calidad);
  const soltarCalidad = useCalidad.subscribe((s, antes) => {
    if (s.calidad !== antes.calidad) aplicarCalidad(s.calidad);
  });
  const selMeshes: THREE.Object3D[] = []; // buffer reusado por frame (sin asignaciones)

  // al grabar, el render tiene un tamaño fijo con DPR 1 (el canvas se ve escalado, sin deformar)
  let fijo: { ancho: number; alto: number } | null = null;
  const resize = () => {
    const w = fijo ? fijo.ancho : mount.clientWidth;
    const h = fijo ? fijo.alto : mount.clientHeight;
    const dpr = fijo ? 1 : window.devicePixelRatio;
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(dpr);
    composer.setPixelRatio(dpr);
    renderer.setSize(w, h, !fijo); // grabando, el estilo del canvas sigue al contenedor
    composer.setSize(w, h); // reajusta RTs y todos los passes (incl. OutlinePass)
  };
  resize();
  const observer = new ResizeObserver(resize);
  observer.observe(mount);

  const tareas: TareaCuadro[] = [];
  const encuadre = crearEncuadreDe(group);
  let frame = 0;
  let vivo = true;
  const prepararCuadro = (ahora: number) => {
    if (!fijo) controls.update(); // al grabar, la cámara la pone el guion
    for (const tarea of tareas) tarea(ahora); // animadores, tinte, tiradores… (antes de componer)
    calidad.ajustar(ahora); // radio de la oclusión y planos de sección (≤ 3 Hz)
    // contorno de selección: recolecta las mallas seleccionadas (robusto a reconstrucciones)
    selMeshes.length = 0;
    for (const id of seleccion()) { const m = meshes.get(id); if (m) selMeshes.push(m); }
    outlinePass.selectedObjects = selMeshes;
    destello.actualizar(meshes, Date.now()); // late ~3 s desde el pulso del visor
    // al final: el guion de la grabación ya puso la cámara. Vale para el visor y para el video
    const enc = encuadre();
    if (enc) ajustarRecorte(camera, enc.esfera, enc.pisoZ); // sin z-fighting a distancia
  };
  const componer = () => {
    composer.render(); // escena + contorno (reemplaza renderer.render)
    if (!fijo) viewCube.render(renderer, camera); // sobre el frame ya compuesto (autoClear=false)
  };
  const animate = () => {
    frame = requestAnimationFrame(animate);
    prepararCuadro(performance.now());
    componer();
  };

  return {
    renderer, scene, camera, controls, gizmo, group, meshes, dir, ground, viewCube, calidad,
    composer, pases: { render: renderPass, contorno: outlinePass, destello: destello.pass },
    ayudantes: [grid, ejes, gizmoObj], aplicarCalidad, prepararCuadro, componer,
    antesDeComponer: (tarea) => { tareas.push(tarea); },
    arrancar: animate,
    modoGrabacion: (tam) => {
      cancelAnimationFrame(frame);
      fijo = tam;
      renderer.domElement.style.objectFit = tam ? "contain" : "";
      resize();
      if (!tam && vivo) animate();
    },
    detener: () => {
      vivo = false;
      cancelAnimationFrame(frame);
      observer.disconnect();
    },
    dispose: () => {
      soltarCalidad();
      gizmo.dispose();
      entorno.dispose();
      calidad.dispose();
      viewCube.dispose();
      outlinePass.dispose();
      destello.dispose();
      composer.dispose(); // libera sus render-targets (incl. composerRT)
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    },
  };
}
