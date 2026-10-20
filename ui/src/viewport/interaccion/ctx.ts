import type { MutableRefObject, RefObject } from "react";
import type * as THREE from "three";
import type { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import type { FeatureOut } from "../../types";
import type { Vcb } from "../EstadoViewport";
import type { ViewCube } from "../viewcube";

/* Contextos del visor (plan piso-con-sombra, D1). Cada módulo de interacción es una función
   `instalarX(ctx) → limpieza` que recibe TODO lo que usa por aquí: nada de cierres sobre
   variables sueltas del efecto de montaje de Viewport.tsx. */

/** Lo que el componente guarda en `ctxRef` y leen sus efectos de React. */
export interface VistaCtx {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  gizmo: TransformControls;
  renderer: THREE.WebGLRenderer;
  group: THREE.Group;
  meshes: Map<string, THREE.Mesh>;
  dir: THREE.DirectionalLight;
  ground: THREE.Mesh;
  handles: THREE.Group; // tiradores de cara/Z de la caja seleccionada (F4B)
}

/** El `Ctx` explícito de `interaccion/`: la vista más los refs y callbacks del componente. */
export interface CtxInteraccion extends VistaCtx {
  mount: HTMLDivElement;
  viewCube: ViewCube;
  /** Uno solo para selección, manipulación y ergonomía (como antes de partir el archivo). */
  raycaster: THREE.Raycaster;
  boxRef: RefObject<HTMLDivElement>; // recuadro de selección
  liveAngleRef: RefObject<HTMLSpanElement>; // lectura en vivo (sin re-render)
  featuresRef: MutableRefObject<FeatureOut[]>;
  blockedRef: MutableRefObject<string[]>; // piezas con guardado fallido
  lastAxisRef: MutableRefObject<string | null>; // eje activo del gizmo
  isGizmoDraggingRef: MutableRefObject<boolean>;
  isBoxSelectingRef: MutableRefObject<boolean>;
  isDraggingObjRef: MutableRefObject<boolean>;
  /** Se arrastra un tirador: el bucle los oculta (lo escribe la manipulación, lo lee el bucle). */
  ocultarTiradores: { current: boolean };
  setVcb: (v: Vcb) => void;
  /* Funciones del componente capturadas en el PRIMER render: sirven porque leen `ctxRef` y
     `selectionRef`, no estado de React. */
  setViewDir: (d: [number, number, number]) => void;
  frameBox: (box: THREE.Box3) => void;
  fitTo: () => void;
}
