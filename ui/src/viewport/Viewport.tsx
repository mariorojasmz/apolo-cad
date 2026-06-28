import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import { selectFeatures, useStore } from "../state/store";
import type { FeatureOut, JointOut } from "../types";
import { buildMesh, type Shading, type SharedGeom } from "./meshes";
import { createGround, createLights, createRenderer, updateGround } from "./scene-setup";
import { setupEnvironment } from "./environment";
import { createViewCube } from "./viewcube";
import { buildProductMeshes, createDropAnimator, disposeProducts, type DropAnimator } from "./products";
import { createGravityAnimator, type GravityAnimator } from "./gravity";
import { installShortcuts, type ShortcutHandlers } from "./shortcuts";
import { installHover } from "./hover";
import Spinner from "../ui/Spinner";

type GizmoMode = "off" | "translate" | "rotate";
type SectionAxis = "" | "x" | "y" | "z";

const VIEWS: Record<string, [number, number, number]> = {
  ISO: [1, -1, 0.8],
  Frente: [0, -1, 0.0001],
  Lateral: [1, 0, 0.0001],
  Planta: [0, 0, 1],
};

interface Ctx {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  gizmo: TransformControls;
  renderer: THREE.WebGLRenderer;
  group: THREE.Group;
  meshes: Map<string, THREE.Mesh>;
  dir: THREE.DirectionalLight;
  ground: THREE.Mesh;
}

/* Orquestador del viewport. El render PBR (renderer/luces/suelo/sombras, IBL,
   materiales por catálogo) y el ViewCube viven en módulos (scene-setup,
   environment, materials, meshes, viewcube). Los sistemas interactivos
   (picking, box-select, medición, sección, cinemática, gizmo) siguen aquí por
   ahora — pendientes de extraer a sus propios módulos (follow-up del mandato de
   escala; se dejaron intactos para no arriesgar regresiones en esta fase). */
export default function Viewport() {
  const mountRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const ctxRef = useRef<Ctx | null>(null);

  const features = useStore(selectFeatures);
  const definitions = useStore((s) => s.scene?.definitions ?? null);
  const selection = useStore((s) => s.selection);
  const kinJoints = useStore((s) => s.kinematics?.joints ?? null);
  const jointValues = useStore((s) => s.jointValues);
  const picking = useStore((s) => s.pickRequest !== null);
  const busy = useStore((s) => s.busy);
  const blocking = useStore((s) => s.blocking);
  const catalog = useStore((s) => s.catalog);
  const physicsResult = useStore((s) => s.physicsResult);
  const physicsToken = useStore((s) => s.physicsToken);
  const gravityResult = useStore((s) => s.gravityResult);
  const gravityToken = useStore((s) => s.gravityToken);
  const projectId = useStore((s) => s.scene?.document.project_id ?? null);
  const [shading, setShading] = useState<Shading>("solid");
  const [gizmoMode, setGizmoMode] = useState<GizmoMode>("off");
  const [rotAxis, setRotAxis] = useState<"x" | "y" | "z">("z");
  const [snapDeg, setSnapDeg] = useState(45); // snap del gizmo al arrastrar (0 = libre)
  const [rotInput, setRotInput] = useState("45");
  const liveAngleRef = useRef<HTMLSpanElement>(null); // lectura de ángulo en vivo (sin re-render)
  const [sectionAxis, setSectionAxis] = useState<SectionAxis>("");
  const [sectionPos, setSectionPos] = useState(50);
  const [measure, setMeasure] = useState<{ p1: number[]; p2: number[] } | null>(null);
  const measureObjRef = useRef<THREE.Object3D | null>(null);
  const productsGroupRef = useRef<THREE.Group | null>(null);
  const dropAnimRef = useRef<DropAnimator | null>(null);
  const gravityAnimRef = useRef<GravityAnimator | null>(null);
  const gravityRestoreRef = useRef<(() => void) | null>(null);
  // ergonomía: refs vivos para que los listeners (instalados una vez) y los atajos
  // lean siempre el estado actual sin reinstalarse.
  const isGizmoDraggingRef = useRef(false);
  const isBoxSelectingRef = useRef(false);
  const didFitRef = useRef(false);
  const handlersRef = useRef<ShortcutHandlers | null>(null);

  const featuresRef = useRef(features);
  featuresRef.current = features;
  const selectionRef = useRef(selection);
  selectionRef.current = selection;

  // ------------------------------------------------------------ montaje three
  useEffect(() => {
    const mount = mountRef.current!;
    const renderer = createRenderer();
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, 1, 1, 100000);
    camera.up.set(0, 0, 1);
    camera.position.set(900, -900, 700);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.zoomToCursor = true; // zoom hacia el cursor (estilo CAD)

    const { dir } = createLights(scene);
    const ground = createGround(scene);
    const disposeEnv = setupEnvironment(renderer, scene);
    const viewCube = createViewCube();

    const grid = new THREE.GridHelper(4000, 80, 0x4a5160, 0x2c313b);
    grid.rotation.x = Math.PI / 2;
    scene.add(grid);
    scene.add(new THREE.AxesHelper(220));

    const group = new THREE.Group();
    scene.add(group);

    const gizmo = new TransformControls(camera, renderer.domElement);
    gizmo.setSpace("world");
    const gizmoObj = (gizmo as unknown as { getHelper?: () => THREE.Object3D }).getHelper?.() ??
      (gizmo as unknown as THREE.Object3D);
    scene.add(gizmoObj);

    gizmo.addEventListener("dragging-changed", (e) => {
      const dragging = Boolean((e as { value?: unknown }).value);
      isGizmoDraggingRef.current = dragging;
      controls.enabled = !dragging;
      if (!dragging) {
        commitGizmo();
        if (liveAngleRef.current) liveAngleRef.current.textContent = "";
      }
    });

    // lectura de ángulo EN VIVO mientras se arrastra el anillo de rotación (HUD, sin re-render)
    gizmo.addEventListener("objectChange", () => {
      const mesh = gizmo.object as THREE.Mesh | undefined;
      if (!isGizmoDraggingRef.current || !mesh || gizmo.getMode() !== "rotate") return;
      const q0 = mesh.userData.q0 as THREE.Quaternion;
      const qd = mesh.quaternion.clone().multiply(q0.clone().invert());
      const ang = THREE.MathUtils.radToDeg(2 * Math.acos(Math.min(1, Math.abs(qd.w))));
      if (liveAngleRef.current) liveAngleRef.current.textContent = ang > 0.05 ? `↻ ${ang.toFixed(1)}°` : "";
    });

    const ctx: Ctx = { scene, camera, controls, gizmo, renderer, group, meshes: new Map(), dir, ground };
    ctxRef.current = ctx;

    function commitGizmo() {
      const mesh = gizmo.object as THREE.Mesh | undefined;
      if (!mesh) return;
      const p0 = mesh.userData.p0 as THREE.Vector3;
      const q0 = mesh.userData.q0 as THREE.Quaternion;
      const dx = mesh.position.x - p0.x;
      const dy = mesh.position.y - p0.y;
      const dz = mesh.position.z - p0.z;
      const qDelta = mesh.quaternion.clone().multiply(q0.clone().invert());
      const euler = new THREE.Euler().setFromQuaternion(qDelta, "XYZ");
      const rx = THREE.MathUtils.radToDeg(euler.x);
      const ry = THREE.MathUtils.radToDeg(euler.y);
      const rz = THREE.MathUtils.radToDeg(euler.z);
      const moved = Math.hypot(dx, dy, dz) > 1e-3;
      const rotated = Math.abs(rx) + Math.abs(ry) + Math.abs(rz) > 1e-3;
      if (!moved && !rotated) return;
      const round3 = (v: number) => Math.round(v * 1000) / 1000;
      void useStore.getState().runCommand("transform", {
        feature: mesh.userData.featureId,
        translate: { x: round3(dx), y: round3(dy), z: round3(dz) },
        rotate: { x: round3(rx), y: round3(ry), z: round3(rz) },
      });
    }

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = mount;
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    let frame = 0;
    const animate = () => {
      frame = requestAnimationFrame(animate);
      controls.update();
      dropAnimRef.current?.tick(performance.now()); // anima las cajas del drop-test
      gravityAnimRef.current?.tick(performance.now()); // anima la caída de las mallas reales
      renderer.render(scene, camera);
      viewCube.render(renderer, camera);
    };
    animate();

    // ------------------------------------------------- selección por clic
    const raycaster = new THREE.Raycaster();
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
      const hits = raycaster.intersectObjects(group.children, false);
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

    // -------------------------------------------- selección por recuadro
    let boxStart: [number, number] | null = null;
    const onPointerDown = (e: PointerEvent) => {
      if (!e.shiftKey || e.button !== 0) return;
      boxStart = [e.clientX, e.clientY];
      isBoxSelectingRef.current = true;
      controls.enabled = false;
      e.preventDefault();
    };
    const onPointerMove = (e: PointerEvent) => {
      const box = boxRef.current;
      if (!boxStart || !box) return;
      const rect = mount.getBoundingClientRect();
      const x1 = Math.min(boxStart[0], e.clientX) - rect.left;
      const y1 = Math.min(boxStart[1], e.clientY) - rect.top;
      box.style.display = "block";
      box.style.left = `${x1}px`;
      box.style.top = `${y1}px`;
      box.style.width = `${Math.abs(e.clientX - boxStart[0])}px`;
      box.style.height = `${Math.abs(e.clientY - boxStart[1])}px`;
    };
    const onPointerUp = (e: PointerEvent) => {
      if (!boxStart) return;
      const [sx, sy] = boxStart;
      boxStart = null;
      isBoxSelectingRef.current = false;
      controls.enabled = !(gizmo as unknown as { dragging?: boolean }).dragging;
      if (boxRef.current) boxRef.current.style.display = "none";
      if (Math.hypot(e.clientX - sx, e.clientY - sy) < 6) return;

      const rect = renderer.domElement.getBoundingClientRect();
      const minX = Math.min(sx, e.clientX);
      const maxX = Math.max(sx, e.clientX);
      const minY = Math.min(sy, e.clientY);
      const maxY = Math.max(sy, e.clientY);

      const ids: string[] = [];
      for (const feat of featuresRef.current) {
        if (!feat.visible) continue;
        const [ax, ay, az] = feat.bbox.min;
        const [bx, by, bz] = feat.bbox.max;
        const corners = [
          [ax, ay, az], [bx, ay, az], [ax, by, az], [bx, by, az],
          [ax, ay, bz], [bx, ay, bz], [ax, by, bz], [bx, by, bz],
        ];
        const inside = corners.some(([x, y, z]) => {
          const p = new THREE.Vector3(x, y, z).project(camera);
          if (p.z < -1 || p.z > 1) return false;
          const px = rect.left + ((p.x + 1) / 2) * rect.width;
          const py = rect.top + ((1 - p.y) / 2) * rect.height;
          return px >= minX && px <= maxX && py >= minY && py <= maxY;
        });
        if (inside) ids.push(feat.id);
      }
      const store = useStore.getState();
      store.select(e.ctrlKey || e.metaKey ? [...new Set([...store.selection, ...ids])] : ids);
    };

    renderer.domElement.addEventListener("mousedown", onDown);
    renderer.domElement.addEventListener("click", onClick);
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);

    // -------- ergonomía: menú contextual, doble-clic enfoca, hover, encuadre ----
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
    const onContext = (e: MouseEvent) => {
      e.preventDefault();
      const id = pickAt(e);
      const store = useStore.getState();
      if (id && !store.selection.includes(id)) store.select([id]);
      store.openContextMenu({ x: e.clientX, y: e.clientY, targetId: id });
    };
    const onDblClick = (e: MouseEvent) => {
      const id = pickAt(e);
      if (!id) return;
      useStore.getState().select([id]);
      const mesh = ctx.meshes.get(id);
      if (mesh) frameBox(new THREE.Box3().setFromObject(mesh));
    };
    const onFitEvent = (ev: Event) => {
      const id = (ev as CustomEvent).detail?.id as string | undefined;
      const mesh = id ? ctx.meshes.get(id) : null;
      if (mesh) frameBox(new THREE.Box3().setFromObject(mesh));
      else fitTo();
    };
    renderer.domElement.addEventListener("contextmenu", onContext);
    renderer.domElement.addEventListener("dblclick", onDblClick);
    window.addEventListener("apolo:fit", onFitEvent as EventListener);
    const disposeHover = installHover({
      dom: renderer.domElement,
      camera,
      group,
      isBusy: () => isGizmoDraggingRef.current || isBoxSelectingRef.current,
      isSelected: (fid) => selectionRef.current.includes(fid),
    });

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      renderer.domElement.removeEventListener("mousedown", onDown);
      renderer.domElement.removeEventListener("click", onClick);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("contextmenu", onContext);
      renderer.domElement.removeEventListener("dblclick", onDblClick);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("apolo:fit", onFitEvent as EventListener);
      disposeHover();
      dropAnimRef.current = null;
      gravityAnimRef.current = null;
      gravityRestoreRef.current?.();
      gravityRestoreRef.current = null;
      if (productsGroupRef.current) {
        disposeProducts(productsGroupRef.current);
        scene.remove(productsGroupRef.current);
        productsGroupRef.current = null;
      }
      gizmo.dispose();
      disposeEnv();
      viewCube.dispose();
      renderer.dispose();
      mount.removeChild(renderer.domElement);
      ctxRef.current = null;
    };
  }, []);

  // ------------------------------------------------------- reconstruir mallas
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    ctx.gizmo.detach();
    ctx.group.clear();
    ctx.meshes.clear();
    const planes = sectionPlanes(sectionAxis, sectionPos, features);
    const catalogByRef = new Map(catalog.map((c) => [c.ref, c]));
    // geometrías compartidas por definición (instancias): una sola por clave
    const shared = new Map<string, SharedGeom>();
    for (const feat of features) {
      if (!feat.visible) continue;
      const mesh = buildMesh(feat, shading, planes, definitions, shared, catalogByRef);
      ctx.meshes.set(feat.id, mesh);
      ctx.group.add(mesh);
    }
    applySelection(ctx.meshes, selection);
    applyKinematicPoses(ctx.meshes, kinJoints, jointValues);
    attachGizmo(ctx, selection, gizmoMode, jointValues);
    updateGround(ctx.ground, ctx.dir, new THREE.Box3().setFromObject(ctx.group));
  }, [features, definitions, shading, sectionAxis, sectionPos, catalog]);

  // ------------------------------------------------------ selección y gizmo
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    applySelection(ctx.meshes, selection);
    attachGizmo(ctx, selection, gizmoMode, jointValues);
  }, [selection, gizmoMode]);

  // ----------------------------------------- pose cinemática (previsualización)
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    applyKinematicPoses(ctx.meshes, kinJoints, jointValues);
    attachGizmo(ctx, selection, gizmoMode, jointValues);
    updateGround(ctx.ground, ctx.dir, new THREE.Box3().setFromObject(ctx.group));
  }, [kinJoints, jointValues]);

  // ------------------------------------------------------------ medición
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    if (measureObjRef.current) {
      ctx.scene.remove(measureObjRef.current);
      measureObjRef.current = null;
    }
    if (!measure) return;
    const a = new THREE.Vector3(...(measure.p1 as [number, number, number]));
    const b = new THREE.Vector3(...(measure.p2 as [number, number, number]));
    const group = new THREE.Group();
    group.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([a, b]),
        new THREE.LineBasicMaterial({ color: 0xffc04d, depthTest: false }),
      ),
    );
    for (const p of [a, b]) {
      const dot = new THREE.Mesh(
        new THREE.SphereGeometry(4, 12, 12),
        new THREE.MeshBasicMaterial({ color: 0xffc04d, depthTest: false }),
      );
      dot.position.copy(p);
      group.add(dot);
    }
    group.renderOrder = 99;
    ctx.scene.add(group);
    measureObjRef.current = group;
  }, [measure]);

  // -------------------------------------------- física: cajas del drop-test
  // Overlay efímero (patrón medición). Las cajas van a ctx.scene (NO a ctx.group)
  // → fuera del raycast de selección/box-select. El animador las mueve en el rAF.
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    dropAnimRef.current = null;
    if (productsGroupRef.current) {
      disposeProducts(productsGroupRef.current);
      ctx.scene.remove(productsGroupRef.current);
      productsGroupRef.current = null;
    }
    const modelBox = new THREE.Box3().setFromObject(ctx.group);
    if (!physicsResult || physicsResult.products.length === 0) {
      updateGround(ctx.ground, ctx.dir, modelBox); // restaura el suelo al modelo
      return;
    }
    const group = new THREE.Group();
    const meshes = buildProductMeshes(physicsResult, group);
    ctx.scene.add(group);
    productsGroupRef.current = group;
    dropAnimRef.current = createDropAnimator(
      physicsResult,
      meshes,
      () => {
        const s = useStore.getState();
        return { playing: s.physicsPlaying, speed: s.physicsSpeed };
      },
      () => useStore.getState().setPhysicsPlaying(false),
    );
    // frustum de sombra que cubra también la altura de caída
    updateGround(ctx.ground, ctx.dir, modelBox.union(new THREE.Box3().setFromObject(group)));
  }, [physicsResult, physicsToken]);

  // Caída por gravedad: anima las MALLAS REALES de ctx.meshes (no overlay). Al limpiar/
  // recambiar restaura las mallas tocadas. clearGravity() (open/new/refresh) → restaura.
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    gravityAnimRef.current = null;
    gravityRestoreRef.current?.(); // restaura las mallas del animador anterior
    gravityRestoreRef.current = null;
    if (!gravityResult || gravityResult.products.length === 0) return;
    const { animator, restore } = createGravityAnimator(
      gravityResult,
      ctx.meshes,
      () => {
        const s = useStore.getState();
        return { playing: s.gravityPlaying, speed: s.gravitySpeed };
      },
      () => useStore.getState().setGravityPlaying(false),
    );
    gravityAnimRef.current = animator;
    gravityRestoreRef.current = restore;
  }, [gravityResult, gravityToken]);

  const startMeasure = () => {
    setMeasure(null);
    const store = useStore.getState();
    store.requestPick((p1) => {
      useStore.getState().requestPick((p2) => setMeasure({ p1: [...p1], p2: [...p2] }));
    });
  };

  const measureDist = measure
    ? Math.hypot(
        measure.p2[0] - measure.p1[0],
        measure.p2[1] - measure.p1[1],
        measure.p2[2] - measure.p1[2],
      )
    : 0;

  // Encuadra una caja: mantiene la dirección actual de la cámara salvo que se dé `dir`.
  const frameBox = (box: THREE.Box3, dir?: [number, number, number]) => {
    const ctx = ctxRef.current;
    if (!ctx || box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length() || 1200;
    const v = dir
      ? new THREE.Vector3(...dir).normalize().multiplyScalar(size * 1.4)
      : ctx.camera.position.clone().sub(ctx.controls.target).normalize().multiplyScalar(size * 1.4);
    ctx.camera.position.copy(center.clone().add(v));
    ctx.controls.target.copy(center);
    ctx.controls.update();
  };
  const selectionBox = (): THREE.Box3 | null => {
    const ctx = ctxRef.current;
    if (!ctx) return null;
    const box = new THREE.Box3();
    let any = false;
    for (const id of selectionRef.current) {
      const mesh = ctx.meshes.get(id);
      if (mesh) { box.expandByObject(mesh); any = true; }
    }
    return any ? box : null;
  };
  const fitTo = () => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    frameBox(selectionBox() ?? new THREE.Box3().setFromObject(ctx.group));
  };
  const setViewDir = (d: [number, number, number]) => {
    const ctx = ctxRef.current;
    if (ctx) frameBox(new THREE.Box3().setFromObject(ctx.group), d);
  };
  const setView = (name: keyof typeof VIEWS) => setViewDir(VIEWS[name]);

  // atajos de teclado: handlers refrescados cada render (setters estables + fitTo);
  // el listener se instala una vez y los lee por getter (sin closures viejos).
  handlersRef.current = {
    fitTo,
    setView: (name) => setView(name),
    toggleShading: () => setShading((s) => (s === "solid" ? "wire" : "solid")),
    gizmoMode: () => gizmoMode,
    setGizmo: (m) => setGizmoMode(m),
    cycleSection: () =>
      setSectionAxis((a) => (a === "" ? "x" : a === "x" ? "y" : a === "y" ? "z" : "")),
    toggleMeasure: () => (measure ? setMeasure(null) : startMeasure()),
    nudge: (dx, dy, dz) => void useStore.getState().nudgeSelection(dx, dy, dz),
    isBusy: () => isGizmoDraggingRef.current || isBoxSelectingRef.current,
  };
  useEffect(() => installShortcuts(() => handlersRef.current), []);

  // al cambiar de proyecto, permite re-encuadrar una vez
  useEffect(() => {
    didFitRef.current = false;
  }, [projectId]);

  // encuadre al abrir: la primera vez que hay mallas, enfoca el modelo
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx || didFitRef.current || features.length === 0) return;
    didFitRef.current = true;
    requestAnimationFrame(() => frameBox(new THREE.Box3().setFromObject(ctx.group)));
  }, [features]);

  // snap de rotación del gizmo (al arrastrar el anillo); 0 = libre
  useEffect(() => {
    ctxRef.current?.gizmo.setRotationSnap(snapDeg > 0 ? THREE.MathUtils.degToRad(snapDeg) : null);
  }, [snapDeg]);

  // rotación por ÁNGULO EXACTO sobre el centro del sólido (botones rápidos + numérico)
  const applyRotate = (deg: number) => {
    if (selection.length !== 1 || !Number.isFinite(deg) || deg === 0) return;
    void useStore.getState().runCommand("transform", {
      feature: selection[0],
      rotate: { x: rotAxis === "x" ? deg : 0, y: rotAxis === "y" ? deg : 0, z: rotAxis === "z" ? deg : 0 },
    });
  };

  const selName =
    selection.length === 1
      ? features.find((f) => f.id === selection[0])?.name ?? selection[0]
      : selection.length > 1
        ? `${selection.length} sólidos`
        : "";

  // caja envolvente de la selección (ancho × fondo × alto) — visible al multiseleccionar
  const selExtent = (() => {
    if (selection.length === 0) return "";
    const sel = features.filter((f) => selection.includes(f.id));
    if (sel.length === 0) return "";
    const min = [Infinity, Infinity, Infinity];
    const max = [-Infinity, -Infinity, -Infinity];
    for (const f of sel)
      for (let i = 0; i < 3; i++) {
        min[i] = Math.min(min[i], f.bbox.min[i]);
        max[i] = Math.max(max[i], f.bbox.max[i]);
      }
    const d = max.map((v, i) => Math.round(v - min[i]));
    return `▢ ${d[0]} × ${d[1]} × ${d[2]} mm`;
  })();

  return (
    <div className={`viewport${picking ? " picking" : ""}`} ref={mountRef}>
      {picking && <div className="pick-banner">📍 Haz clic sobre el sólido para elegir el punto</div>}
      {busy && !blocking && !picking && (
        <div className="viewport-busy">
          <Spinner size={13} />
          Actualizando…
        </div>
      )}
      <div className="box-select" ref={boxRef} />
      <div className="viewport-overlay">
        {Object.keys(VIEWS).map((name) => (
          <button key={name} onClick={() => setView(name as keyof typeof VIEWS)}>
            {name}
          </button>
        ))}
        <button onClick={() => setShading(shading === "solid" ? "wire" : "solid")}>
          {shading === "solid" ? "Alambre" : "Sólido"}
        </button>
        <span className="overlay-sep" />
        <button
          className={gizmoMode === "translate" ? "active" : ""}
          title="Arrastra el gizmo para mover el sólido seleccionado"
          onClick={() => setGizmoMode(gizmoMode === "translate" ? "off" : "translate")}
        >
          Mover
        </button>
        <button
          className={gizmoMode === "rotate" ? "active" : ""}
          title="Arrastra el gizmo para rotar el sólido seleccionado"
          onClick={() => setGizmoMode(gizmoMode === "rotate" ? "off" : "rotate")}
        >
          Rotar
        </button>
        <span className="overlay-sep" />
        <button
          className={measure || picking ? "active" : ""}
          title="Medir distancia entre dos puntos (clic en dos sólidos)"
          onClick={() => (measure ? setMeasure(null) : startMeasure())}
        >
          📏 {measure ? "Borrar" : "Medir"}
        </button>
        <button
          className={sectionAxis ? "active" : ""}
          title="Plano de sección"
          onClick={() =>
            setSectionAxis(sectionAxis === "" ? "x" : sectionAxis === "x" ? "y" : sectionAxis === "y" ? "z" : "")
          }
        >
          Sección{sectionAxis ? ` ${sectionAxis.toUpperCase()}` : ""}
        </button>
        {sectionAxis && (
          <input
            type="range"
            min={0}
            max={100}
            value={sectionPos}
            onChange={(e) => setSectionPos(Number(e.target.value))}
          />
        )}
      </div>
      {gizmoMode === "rotate" && (
        <div className="rotate-panel">
          <span className="rp-label">Eje</span>
          {(["x", "y", "z"] as const).map((a) => (
            <button
              key={a}
              className={`rp-axis rp-${a}${rotAxis === a ? " active" : ""}`}
              title={`Rotar sobre el eje ${a.toUpperCase()}`}
              onClick={() => setRotAxis(a)}
            >
              {a.toUpperCase()}
            </button>
          ))}
          <span className="overlay-sep" />
          {[-90, -45, 45, 90, 180].map((d) => (
            <button
              key={d}
              disabled={selection.length !== 1}
              title={`Rotar ${d > 0 ? "+" : ""}${d}° sobre ${rotAxis.toUpperCase()} (centro del sólido)`}
              onClick={() => applyRotate(d)}
            >
              {d > 0 ? `+${d}` : d}°
            </button>
          ))}
          <span className="overlay-sep" />
          <input
            className="rp-input"
            type="number"
            step={5}
            value={rotInput}
            title="Ángulo exacto en grados"
            onChange={(e) => setRotInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") applyRotate(Number(rotInput));
            }}
          />
          <button disabled={selection.length !== 1} onClick={() => applyRotate(Number(rotInput))}>
            Aplicar °
          </button>
          <span className="overlay-sep" />
          <span className="rp-label">Snap</span>
          {[0, 15, 45, 90].map((s) => (
            <button
              key={s}
              className={snapDeg === s ? "active" : ""}
              title={s === 0 ? "Arrastre libre (sin snap)" : `Arrastrar el anillo salta de ${s}° en ${s}°`}
              onClick={() => setSnapDeg(s)}
            >
              {s === 0 ? "Off" : `${s}°`}
            </button>
          ))}
        </div>
      )}
      <div className="viewport-status">
        mm · {features.filter((f) => f.visible).length} sólidos
        {selName ? ` · selección: ${selName}` : ""}
        {selExtent ? ` · ${selExtent}` : ""}
        <span ref={liveAngleRef} className="live-angle" />
        {gizmoMode !== "off" && selection.length !== 1 ? " · el gizmo necesita un único sólido" : ""}
        {measure
          ? ` · 📏 ${measureDist.toFixed(1)} mm (ΔX ${(measure.p2[0] - measure.p1[0]).toFixed(1)}, ΔY ${(
              measure.p2[1] - measure.p1[1]
            ).toFixed(1)}, ΔZ ${(measure.p2[2] - measure.p1[2]).toFixed(1)})`
          : ""}
      </div>
    </div>
  );
}

function sectionPlanes(axis: SectionAxis, pos: number, features: FeatureOut[]): THREE.Plane[] {
  if (!axis || features.length === 0) return [];
  const idx = axis === "x" ? 0 : axis === "y" ? 1 : 2;
  let min = Infinity;
  let max = -Infinity;
  for (const f of features) {
    if (!f.visible) continue;
    min = Math.min(min, f.bbox.min[idx]);
    max = Math.max(max, f.bbox.max[idx]);
  }
  if (!Number.isFinite(min)) return [];
  const d = min + ((max - min) * pos) / 100 + 0.01;
  const normal = new THREE.Vector3(
    axis === "x" ? -1 : 0,
    axis === "y" ? -1 : 0,
    axis === "z" ? -1 : 0,
  );
  return [new THREE.Plane(normal, d)];
}

function applySelection(meshes: Map<string, THREE.Mesh>, selection: string[]) {
  const set = new Set(selection);
  for (const [id, mesh] of meshes) {
    const mat = mesh.material as THREE.MeshStandardMaterial;
    mat.emissive.set(set.has(id) ? 0x3a6fd8 : 0x000000);
    mat.emissiveIntensity = set.has(id) ? 0.55 : 0;
  }
}

function attachGizmo(ctx: Ctx, selection: string[], mode: GizmoMode, jointValues: Record<string, number>) {
  const posing = Object.values(jointValues).some((v) => v !== 0);
  if (mode === "off" || selection.length !== 1 || posing) {
    ctx.gizmo.detach();
    return;
  }
  const mesh = ctx.meshes.get(selection[0]);
  if (!mesh) {
    ctx.gizmo.detach();
    return;
  }
  ctx.gizmo.setMode(mode);
  ctx.gizmo.attach(mesh);
}

/* Cinemática directa (solo visual): pose(hijo) = pose(padre) · T(o) · R(eje, v) · T(-o) */
function computePoses(joints: JointOut[], values: Record<string, number>): Map<string, THREE.Matrix4> {
  const byChild = new Map(joints.map((j) => [j.child, j]));
  const memo = new Map<string, THREE.Matrix4>();

  const poseFor = (id: string, depth = 0): THREE.Matrix4 => {
    const cached = memo.get(id);
    if (cached) return cached;
    const joint = byChild.get(id);
    let m: THREE.Matrix4;
    if (!joint || depth > 64) {
      m = new THREE.Matrix4();
    } else {
      const parent = poseFor(joint.parent, depth + 1);
      const v = values[joint.name] ?? 0;
      const local = new THREE.Matrix4();
      if (v !== 0 && joint.type !== "fija") {
        const axis = new THREE.Vector3(joint.axis[0], joint.axis[1], joint.axis[2]).normalize();
        if (joint.type === "prismatica") {
          local.makeTranslation(axis.x * v, axis.y * v, axis.z * v);
        } else {
          const [ox, oy, oz] = joint.origin;
          local
            .makeTranslation(ox, oy, oz)
            .multiply(new THREE.Matrix4().makeRotationAxis(axis, THREE.MathUtils.degToRad(v)))
            .multiply(new THREE.Matrix4().makeTranslation(-ox, -oy, -oz));
        }
      }
      m = parent.clone().multiply(local);
    }
    memo.set(id, m);
    return m;
  };

  for (const j of joints) {
    poseFor(j.parent);
    poseFor(j.child);
  }
  return memo;
}

const IDENTITY = new THREE.Matrix4();

function applyKinematicPoses(
  meshes: Map<string, THREE.Mesh>,
  joints: JointOut[] | null,
  values: Record<string, number>,
) {
  const posing = !!joints && Object.values(values).some((v) => v !== 0);
  const poses = posing ? computePoses(joints!, values) : null;

  for (const [id, mesh] of meshes) {
    const base = mesh.userData.baseMatrix as THREE.Matrix4;
    const pose = poses?.get(id);
    if (pose && !pose.equals(IDENTITY)) {
      mesh.matrixAutoUpdate = false;
      mesh.matrix.copy(pose).multiply(base);
      mesh.matrixWorldNeedsUpdate = true;
    } else if (!mesh.matrixAutoUpdate) {
      mesh.matrixAutoUpdate = true;
      mesh.position.copy(mesh.userData.p0 as THREE.Vector3);
      mesh.quaternion.copy(mesh.userData.q0 as THREE.Quaternion);
      mesh.updateMatrix();
    }
  }
}
