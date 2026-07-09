import { useEffect, useRef, useState } from "react";
import { Copy, Crop, EyeOff, Focus, Trash2 } from "lucide-react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import { queuedEditParams, selectFeatures, useStore } from "../state/store";
import type { FeatureOut, JointOut } from "../types";
import {
  applyAppearance, appearanceSig, buildMesh, disposeMesh, disposeSharedGeom,
  type Shading, type SharedGeom,
} from "./meshes";
import { BACKGROUND_CSS, createGround, createLights, createRenderer, updateGround } from "./scene-setup";
import { setupEnvironment } from "./environment";
import { createViewCube } from "./viewcube";
import { buildProductMeshes, createDropAnimator, disposeProducts, type DropAnimator } from "./products";
import { createGravityAnimator, type GravityAnimator } from "./gravity";
import { installShortcuts, type ShortcutHandlers } from "./shortcuts";
import { installGltfExport } from "./exportGltf";
import { buildSnapIndex, movingOffsets, nearestScreenSnap, type SnapPoint } from "./snap";
import { distanceAlongAxis, rayPlanePoint } from "./pushpull";
import { anglePointOnAxis, axisBasis, baseHandles, boxDimsFromBbox, heightHandlePos, ROT_CANDIDATES, rotArrowPlacement, shortestAngleDiff, snapAngleByDistance, zLiftPoint, type StretchAffect } from "./handles";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { OutlinePass } from "three/examples/jsm/postprocessing/OutlinePass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { makeHandleSprite, squareDarkTex, squareLightTex } from "./handleSprites";
import Spinner from "../ui/Spinner";

/** Flecha de rotación 3D de tamaño UNIDAD (radio 1): arco (torus parcial) + una punta de cono
   en cada extremo (doble sentido). Singleton compartido; Viewport la orienta al plano ⟂ eje y
   la escala por frame a tamaño de pantalla constante. Su PERSPECTIVA indica qué rotación aplica. */
let _rotArrow: THREE.BufferGeometry | null = null;
// Flecha de rotación PLANA (2D, estilo TinkerCad): banda curva + 2 puntas triangulares, todo en el
// plano local XY (z=0). La orientación 3D la da el overlay (makeBasis). Material DoubleSide → visible
// por ambos lados al orbitar.
function rotArrowGeom(): THREE.BufferGeometry {
  if (_rotArrow) return _rotArrow;
  const R = 1, w2 = 0.08, span = Math.PI * 0.6; // arco ~108°, media-anchura de la banda
  const headHalfW = 0.24, headLen = 0.5;
  const parts: THREE.BufferGeometry[] = [new THREE.RingGeometry(R - w2, R + w2, 48, 1, 0, span)];
  for (const [ang, dir] of [[0, -1], [span, 1]] as [number, number][]) {
    const cx = Math.cos(ang) * R, cy = Math.sin(ang) * R;
    const tx = -Math.sin(ang) * dir, ty = Math.cos(ang) * dir; // tangente (sentido por extremo)
    const rx = Math.cos(ang), ry = Math.sin(ang); // radial
    const tri = new THREE.BufferGeometry();
    tri.setAttribute("position", new THREE.Float32BufferAttribute([
      cx + tx * headLen, cy + ty * headLen, 0, // punta
      cx + rx * headHalfW, cy + ry * headHalfW, 0, // base +
      cx - rx * headHalfW, cy - ry * headHalfW, 0, // base −
    ], 3));
    tri.setAttribute("normal", new THREE.Float32BufferAttribute([0, 0, 1, 0, 0, 1, 0, 0, 1], 3));
    tri.setAttribute("uv", new THREE.Float32BufferAttribute([0.5, 1, 1, 0, 0, 0], 2));
    tri.setIndex([0, 1, 2]);
    parts.push(tri);
  }
  _rotArrow = mergeGeometries(parts, false) ?? new THREE.RingGeometry(R - w2, R + w2, 30, 1, 0, span);
  parts.forEach((p) => p.dispose());
  return _rotArrow;
}

// Región de CLIC amplia (invisible) alrededor del arco: un anillo grueso que abarca el arco + margen
// → mucho más fácil de agarrar que la banda fina de la flecha. Comparte pose y userData con la flecha.
let _rotHit: THREE.BufferGeometry | null = null;
function rotHitGeom(): THREE.BufferGeometry {
  return (_rotHit ??= new THREE.RingGeometry(0.3, 1.75, 24, 1, -0.45, Math.PI * 0.6 + 0.9));
}

// Cono de elevación Z (F4B) + anillos de rotación (F4C). Los tiradores de estirón son SPRITES
// (handleSprites.ts): cuadritos con borde, tamaño de pantalla constante (escala por frame).
const ZCONE_GEOM = new THREE.ConeGeometry(0.55, 1.3, 18).rotateX(Math.PI / 2); // tamaño UNIDAD, apunta +Z (lo escala el loop a px constantes)
const ZCONE_MAT = new THREE.MeshBasicMaterial({ color: 0x63e6ff, depthTest: false });
const WORLD_Z = new THREE.Vector3(0, 0, 1);
const _camRight = new THREE.Vector3(); // scratch: "derecha" de la cámara
const _dRot = new THREE.Vector3(), _yAxis = new THREE.Vector3(), _axisV = new THREE.Vector3(), _mtx = new THREE.Matrix4();
const _zc = new THREE.Vector3(); // scratch: centro-top para el gap del cono Z-lift

/** Coloca UNA flecha de rotación que SIGUE a la cámara. Dos modos:
   - `perp` (azul): arco ⟂ al eje, anclado en la cara lateral ⟂ eje más a la derecha de la cámara
     (patrón `rotArrowPlacement`), a la base.
   - `coplanar` (rojo/verde): arco COPLANAR con la cara del PROPIO eje (⟂ eje = plano de la cara),
     en la cara que MIRA a la cámara, elevado al top; se orienta con la derecha de la cámara
     proyectada a ese plano (+ `tilt`). Evita la degeneración de `perp` cuando la cara ∥ al eje. */
function applyRotArrowPose(mesh: THREE.Object3D, rf: RotFollow, camera: THREE.PerspectiveCamera): void {
  _axisV.set(rf.axis === "x" ? 1 : 0, rf.axis === "y" ? 1 : 0, rf.axis === "z" ? 1 : 0);
  _camRight.set(1, 0, 0).applyQuaternion(camera.quaternion);
  if (rf.mode === "coplanar") {
    const cx = (rf.min[0] + rf.max[0]) / 2, cy = (rf.min[1] + rf.max[1]) / 2, cz = (rf.min[2] + rf.max[2]) / 2;
    const hz = (rf.max[2] - rf.min[2]) / 2;
    const halfA = _axisV.x * (rf.max[0] - rf.min[0]) / 2 + _axisV.y * (rf.max[1] - rf.min[1]) / 2 + _axisV.z * hz;
    const along = _axisV.x * (camera.position.x - cx) + _axisV.y * (camera.position.y - cy) + _axisV.z * (camera.position.z - cz);
    const axRight = _axisV.dot(_camRight); // componente del eje en la "derecha" de la cámara
    // en qué cara ±eje se ancla: FRENTE (a cámara), FONDO (lejos), IZQUIERDA o DERECHA de la cámara
    const sgn = rf.side === "back" ? (along >= 0 ? -1 : 1)
      : rf.side === "left" ? (axRight > 0 ? -1 : 1)
      : rf.side === "right" ? (axRight >= 0 ? 1 : -1)
      : (along >= 0 ? 1 : -1); // "face" (default)
    const off = halfA * (rf.inset ?? 1); // distancia al eje: inset<1 la ACERCA a la línea de centro (0=centro, 1=cara)
    mesh.position.set(cx + _axisV.x * sgn * off, cy + _axisV.y * sgn * off, cz + _axisV.z * sgn * off + rf.zFrac * hz);
    // referencia FIJA (⟂ eje y ⟂ Z-mundo): pone el LOMO del arco hacia arriba → las PUNTAS miran
    // ABAJO. No depende de la cámara → las puntas se quedan mirando abajo SIEMPRE (sin voltearse).
    _dRot.crossVectors(WORLD_Z, _axisV);
    if (_dRot.lengthSq() < 1e-6) _dRot.set(1, 0, 0); // fallback si el eje fuese Z (no aplica a rojo/verde)
    _dRot.normalize().applyAxisAngle(_axisV, rf.tilt);
  } else {
    const pl = rotArrowPlacement(rf.min, rf.max, rf.candidates!, _camRight.x, _camRight.y, _camRight.z, rf.m, rf.zFrac);
    mesh.position.set(pl.pos[0], pl.pos[1], pl.pos[2]);
    _dRot.set(pl.dir[0], pl.dir[1], pl.dir[2]).applyAxisAngle(_axisV, rf.tilt);
  }
  _yAxis.crossVectors(_axisV, _dRot);
  _mtx.makeBasis(_dRot, _yAxis, _axisV); // arco: X→referencia, Z→eje de giro
  mesh.quaternion.setFromRotationMatrix(_mtx);
}
interface RotFollow { min: number[]; max: number[]; axis: "x" | "y" | "z"; m: number; zFrac: number; tilt: number; mode: "perp" | "coplanar"; side?: "face" | "back" | "left" | "right"; inset?: number; candidates?: [number, number, number][]; }
// Anillos de rotación (F4C): color por eje (X rojo / Y verde / Z azul). Geometría por selección
// (radio del bbox) → se dispone al limpiar; los materiales se comparten.
const ROT_MAT: Record<"x" | "y" | "z", THREE.MeshBasicMaterial> = {
  x: new THREE.MeshBasicMaterial({ color: 0xff5a5a, depthTest: false, transparent: true, opacity: 0.85, side: THREE.DoubleSide }),
  y: new THREE.MeshBasicMaterial({ color: 0x5ad15a, depthTest: false, transparent: true, opacity: 0.85, side: THREE.DoubleSide }),
  z: new THREE.MeshBasicMaterial({ color: 0x5a8cff, depthTest: false, transparent: true, opacity: 0.85, side: THREE.DoubleSide }),
};
// material INVISIBLE (pero raycastable) para la región de clic ampliada de las flechas de rotación.
const ROT_HIT_MAT = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthTest: false, depthWrite: false, side: THREE.DoubleSide });

/** Construye el overlay de la pieza seleccionada (flechas + proxies de clic + guías + cuadritos +
   altura + cono) dentro del grupo `g`, a partir de un bbox `min/max` y los params de la caja. Se
   llama desde el useEffect (bbox del servidor) Y al soltar un arrastre (bbox VIVO del preview) →
   así el overlay se actualiza al instante, sin esperar la regeneración del servidor. */
function buildOverlay(
  g: THREE.Group, feat: { command_type?: string | null } | undefined,
  min: number[], max: number[], cmdParams: Record<string, unknown>, camera: THREE.PerspectiveCamera,
): void {
  while (g.children.length) { // sprites/flechas/cono → material propio; guía → geometría propia; las geometrías de flecha/cono son singletons
    const c = g.children[0] as THREE.Sprite & THREE.LineSegments;
    if ((c as THREE.Sprite).isSprite) (c.material as THREE.Material).dispose();
    else if (c.userData?.kind === "guide") c.geometry.dispose();
    else if (c.userData?.ownMat) ((c as unknown as THREE.Mesh).material as THREE.Material).dispose();
    g.remove(c);
  }
  if (!feat) return;
  const center = new THREE.Vector3((min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2);
  const maxExt = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2]);
  const m = maxExt * 0.13 + 12;
  const deg = (d: number) => THREE.MathUtils.degToRad(d);
  const rf: Record<"x" | "y" | "z", Omit<RotFollow, "min" | "max" | "axis" | "m">> = {
    x: { mode: "coplanar", side: "back", zFrac: 1.2, inset: 1, tilt: deg(37.5) },
    y: { mode: "coplanar", side: "back", zFrac: 1.2, inset: 1, tilt: deg(37.5) },
    z: { mode: "perp", zFrac: -1, tilt: deg(-52.5), candidates: ROT_CANDIDATES.z },
  };
  for (const a of ROT_AXES) {
    const follow: RotFollow = { min: [min[0], min[1], min[2]], max: [max[0], max[1], max[2]], axis: a.letter, m, ...rf[a.letter] };
    const ud = { kind: "rot", letter: a.letter, axis: a.axis.toArray(), sizePx: 15, rotFollow: follow };
    const arrowMat = ROT_MAT[a.letter].clone(); // material PROPIO → el hover lo tinta sin tocar el compartido
    const arrow = new THREE.Mesh(rotArrowGeom(), arrowMat); // flecha visible (2D plana)
    arrow.renderOrder = 104;
    arrow.userData = { ...ud, ownMat: true, baseColor: arrowMat.color.getHex(), baseOpacity: arrowMat.opacity, baseRenderOrder: 104 };
    applyRotArrowPose(arrow, follow, camera);
    const hit = new THREE.Mesh(rotHitGeom(), ROT_HIT_MAT); // región de clic ampliada (invisible)
    hit.renderOrder = 103;
    hit.userData = { ...ud, twin: arrow }; // hover sobre la zona ampliada → resalta la flecha visible
    applyRotArrowPose(hit, follow, camera);
    g.add(hit);
    g.add(arrow);
  }
  if (feat.command_type === "create_box" && boxDimsFromBbox(min, max, cmdParams)) {
    g.add(guideLines(min, max)); // rectángulo de base + eje vertical
    for (const bh of baseHandles(min, max)) {
      const sp = makeHandleSprite(bh.kind === "corner" ? squareLightTex() : squareDarkTex(), 0xffffff);
      sp.position.set(bh.pos[0], bh.pos[1], bh.pos[2]);
      Object.assign(sp.userData, { kind: bh.kind, affects: bh.affects, sizePx: 13 });
      g.add(sp);
    }
    const hp = heightHandlePos(min, max, camera.position.z > center.z);
    const hs = makeHandleSprite(squareLightTex(), 0xffffff);
    hs.position.set(hp[0], hp[1], hp[2]);
    Object.assign(hs.userData, { kind: "height", minZ: min[2], maxZ: max[2], cx: hp[0], cy: hp[1], sizePx: 13 });
    g.add(hs);
    const coneMat = ZCONE_MAT.clone(); // material PROPIO → el hover lo tinta sin tocar el compartido
    const cone = new THREE.Mesh(ZCONE_GEOM, coneMat);
    cone.position.copy(zLiftPoint(min, max)); // inicial; el loop lo recoloca (alterna arriba/abajo + gap de pantalla)
    cone.renderOrder = 105;
    // ALTERNA según la cámara (una sola a la vez, siempre visible): arriba=+Z sobre el top, abajo=−Z bajo la
    // base. `armZ` = altura de las flechas de giro (para quedar por ENCIMA). Tamaño/gap de pantalla constante.
    cone.userData = { kind: "zlift", ownMat: true, baseColor: coneMat.color.getHex(), baseOpacity: coneMat.opacity, baseRenderOrder: 105, sizePx: 15, cx: center.x, cy: center.y, topZ: max[2], botZ: min[2], armZ: 0.2 * (max[2] - min[2]) / 2, gapPx: 48 };
    g.add(cone);
  }
}
const ROT_AXES = [
  { letter: "x" as const, axis: new THREE.Vector3(1, 0, 0) },
  { letter: "y" as const, axis: new THREE.Vector3(0, 1, 0) },
  { letter: "z" as const, axis: new THREE.Vector3(0, 0, 1) },
];
// Líneas guía TinkerCad: rectángulo de la base + eje vertical central (base→cuadrito de altura).
// Punteadas, se dibujan SOBRE el sólido (depthTest off) para leer la caja en el espacio. NO
// raycastables (no deben robar el clic a los cuadritos). Material compartido; geometría por caja
// (se dispone en el clear del overlay, marcada con kind:"guide").
const GUIDE_MAT = new THREE.LineDashedMaterial({ color: 0xffffff, dashSize: 7, gapSize: 5, depthTest: false, transparent: true, opacity: 0.5 });
function guideLines(min: number[], max: number[]): THREE.LineSegments {
  const cx = (min[0] + max[0]) / 2, cy = (min[1] + max[1]) / 2, z = min[2], Z = max[2];
  const p = [
    min[0], min[1], z, max[0], min[1], z, // rectángulo de base (4 aristas inferiores)
    max[0], min[1], z, max[0], max[1], z,
    max[0], max[1], z, min[0], max[1], z,
    min[0], max[1], z, min[0], min[1], z,
    cx, cy, z, cx, cy, Z, // eje vertical central
  ];
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
  const ls = new THREE.LineSegments(geo, GUIDE_MAT);
  ls.computeLineDistances(); // requerido por LineDashedMaterial
  ls.renderOrder = 103; // sobre el sólido, bajo los cuadritos (106)
  ls.userData = { kind: "guide" };
  ls.raycast = () => {}; // nunca intercepta el puntero
  return ls;
}

type GizmoMode = "off" | "translate" | "rotate" | "scale";
type SectionAxis = "" | "x" | "y" | "z";

/* VCB (value control box): tras un arrastre del gizmo por un eje, el usuario puede teclear
   el valor EXACTO de ese eje (estilo SketchUp). Robusto porque ocurre TRAS soltar el ratón
   (no pelea con TransformControls, que recalcula cada frame). Rotación no usa VCB: el panel
   de rotación ya tiene grados exactos. */
type Vcb =
  | { mode: "translate"; axis: "x" | "y" | "z"; featureId: string; committedAxisDelta: number }
  | { mode: "scale"; axis: "x" | "y" | "z"; featureId: string; cmdId: string; currentDim: number }
  | null;

const VIEWS: Record<string, [number, number, number]> = {
  ISO: [1, -1, 0.8],
  Frente: [0, -1, 0.0001],
  Lateral: [1, 0, 0.0001],
  Planta: [0, 0, 1],
};

/** Eje del gizmo ("X"/"Y"/"Z") a minúscula; null si es un plano/ambiguo (sin VCB). */
function axisLetter(a: string | null): "x" | "y" | "z" | null {
  return a === "X" ? "x" : a === "Y" ? "y" : a === "Z" ? "z" : null;
}

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
  handles: THREE.Group; // tiradores de cara/Z de la caja seleccionada (F4B)
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
  const snapEnabled = useStore((s) => s.snapEnabled);
  const snapStep = useStore((s) => s.snapStep);
  const toggleSnap = useStore((s) => s.toggleSnap);
  const [shading, setShading] = useState<Shading>("solid");
  const [gizmoMode, setGizmoMode] = useState<GizmoMode>("off");
  const [rotAxis, setRotAxis] = useState<"x" | "y" | "z">("z");
  const [snapDeg, setSnapDeg] = useState(45); // snap del gizmo al arrastrar (0 = libre)
  const [rotInput, setRotInput] = useState("45");
  const [vcb, setVcb] = useState<Vcb>(null); // caja de valor exacto tras un arrastre del gizmo
  const vcbRef = useRef<Vcb>(null);
  vcbRef.current = vcb;
  const lastAxisRef = useRef<string | null>(null); // eje activo del gizmo (capturado en objectChange)
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
  const isDraggingObjRef = useRef(false); // agarrar-y-mover directo (F4A) en curso
  const didFitRef = useRef(false);
  const handlersRef = useRef<ShortcutHandlers | null>(null);
  // reuso de mallas (V6.2b): diff persistente entre pasadas. builtRef = lo construido por
  // fid (rev + firma de apariencia); sharedRef = pool de geometrías de instancia (persiste
  // entre pasadas); buildKeyRef = clave de invalidación TOTAL (shading/sección/catálogo).
  const builtRef = useRef<Map<string, { rev: number; mesh: THREE.Mesh; app: string; key: string | null }>>(new Map());
  const sharedRef = useRef<Map<string, SharedGeom>>(new Map());
  const buildKeyRef = useRef<string>("");
  const buildCountRef = useRef(0); // # de mallas construidas (E2E: verificar reuso, V6.2b)

  const featuresRef = useRef(features);
  featuresRef.current = features;
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const blockedIds = useStore((s) => s.blockedIds); // piezas con guardado fallido (bloqueadas)
  const blockedRef = useRef(blockedIds);
  blockedRef.current = blockedIds;

  // ------------------------------------------------------------ montaje three
  useEffect(() => {
    const mount = mountRef.current!;
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

    // --- snapping del gizmo (Boceto · Fase 2): índice de puntos clave de las otras
    // piezas + marcador del destino activo. Se reconstruye 1× por arrastre (no por frame).
    let snapIndex: SnapPoint[] = [];
    let snapOffsets: THREE.Vector3[] = [];
    let ctrlHeld = false; // mantener Ctrl durante el arrastre desactiva el snap al vuelo
    const snapMarker = new THREE.Mesh(
      new THREE.SphereGeometry(9, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0x63e6ff, depthTest: false }),
    );
    snapMarker.renderOrder = 100;
    snapMarker.visible = false;
    scene.add(snapMarker);
    // mantener Ctrl durante el arrastre = suelta TODO el snap (también la rejilla nativa)
    const onModKey = (e: KeyboardEvent) => {
      ctrlHeld = e.ctrlKey || e.metaKey;
      const st = useStore.getState();
      gizmo.setTranslationSnap(!ctrlHeld && st.snapEnabled ? st.snapStep : null);
    };
    window.addEventListener("keydown", onModKey);
    window.addEventListener("keyup", onModKey);

    gizmo.addEventListener("dragging-changed", (e) => {
      const dragging = Boolean((e as { value?: unknown }).value);
      isGizmoDraggingRef.current = dragging;
      controls.enabled = !dragging;
      if (dragging) {
        setVcb(null); // un gesto nuevo invalida la caja de valor pendiente
        const mesh = gizmo.object as THREE.Mesh | undefined;
        const st = useStore.getState();
        if (mesh && st.snapEnabled) {
          const fid = mesh.userData.featureId as string;
          const feat = featuresRef.current.find((f) => f.id === fid);
          snapIndex = buildSnapIndex(featuresRef.current, fid);
          snapOffsets = feat ? movingOffsets(feat.bbox, mesh.position.clone()) : [];
        } else {
          snapIndex = [];
          snapOffsets = [];
        }
      } else {
        commitGizmo();
        snapIndex = [];
        snapOffsets = [];
        snapMarker.visible = false;
        if (liveAngleRef.current) liveAngleRef.current.textContent = "";
      }
    });

    // HUD EN VIVO al arrastrar (sin re-render) + snapping (rejilla ya la aplica el gizmo
    // vía translationSnap; aquí va la inferencia a puntos de otras piezas y el snap
    // dimensional de la escala). El post-proceso de position/scale tras el gizmo es estable:
    // TransformControls recomputa cada frame desde su _positionStart/_scaleStart (no deriva).
    gizmo.addEventListener("objectChange", () => {
      const mesh = gizmo.object as THREE.Mesh | undefined;
      const hud = liveAngleRef.current;
      if (!isGizmoDraggingRef.current || !mesh || !hud) return;
      const mode = gizmo.getMode();
      lastAxisRef.current = (gizmo as unknown as { axis: string | null }).axis; // eje activo
      const st = useStore.getState();
      const snapping = st.snapEnabled && !ctrlHeld;
      let snapNote = "";
      if (mode === "rotate") {
        const q0 = mesh.userData.q0 as THREE.Quaternion;
        const qd = mesh.quaternion.clone().multiply(q0.clone().invert());
        const ang = THREE.MathUtils.radToDeg(2 * Math.acos(Math.min(1, Math.abs(qd.w))));
        hud.textContent = ang > 0.05 ? `↻ ${ang.toFixed(1)}°` : "";
      } else if (mode === "translate") {
        // inferencia: pega el punto clave más cercano de la caja a un punto de otra pieza
        if (snapping && snapOffsets.length && snapIndex.length) {
          const movingWorld = snapOffsets.map((o) => mesh.position.clone().add(o));
          const rect = renderer.domElement.getBoundingClientRect();
          const hit = nearestScreenSnap(movingWorld, snapIndex, camera, rect, 12);
          if (hit) {
            mesh.position.add(hit.correction);
            snapMarker.position.copy(hit.target.world);
            snapMarker.visible = true;
            snapNote = ` · ▣ ${hit.target.kind} · ${hit.target.name}`;
          } else {
            snapMarker.visible = false;
          }
        }
        const p0 = mesh.userData.p0 as THREE.Vector3;
        hud.textContent =
          `Δ ${(mesh.position.x - p0.x).toFixed(1)}, ${(mesh.position.y - p0.y).toFixed(1)}, ${(mesh.position.z - p0.z).toFixed(1)} mm${snapNote}`;
      } else if (mode === "scale") {
        const b = mesh.userData.boxDims as { w: number; d: number; h: number } | undefined;
        if (b) {
          // snap DIMENSIONAL: redondea la cota resultante a múltiplos de snapStep, solo en
          // el eje que el usuario mueve (scale≠1) para no tocar los que dejó quietos.
          if (snapping) {
            const step = st.snapStep || 1;
            const snapAxis = (base: number, s: number) =>
              Math.abs(s - 1) < 1e-4 ? s : Math.max(step, Math.round((base * s) / step) * step) / base;
            mesh.scale.set(snapAxis(b.w, mesh.scale.x), snapAxis(b.d, mesh.scale.y), snapAxis(b.h, mesh.scale.z));
            snapNote = ` · rejilla ${step}`;
          }
          hud.textContent =
            `${(b.w * mesh.scale.x).toFixed(0)} × ${(b.d * mesh.scale.y).toFixed(0)} × ${(b.h * mesh.scale.z).toFixed(0)} mm${snapNote}`;
        }
      }
    });

    const handlesGroup = new THREE.Group(); // tiradores de la caja seleccionada (F4B)
    scene.add(handlesGroup);
    const ctx: Ctx = { scene, camera, controls, gizmo, renderer, group, meshes: new Map(), dir, ground, handles: handlesGroup };
    ctxRef.current = ctx;
    // ctx fresco → resetea el diff de mallas (V6.2b): builtRef apuntaba al group anterior
    builtRef.current.clear();
    sharedRef.current.clear();
    buildKeyRef.current = "";
    // hook de depuración/E2E (V6.2b): identidad de mallas + contador de builds para
    // verificar el reuso sin depender del screenshot (que se cuelga por el rAF).
    (window as unknown as { __apolo?: unknown }).__apolo = {
      meshIds: () => [...ctx.meshes].map(([id, m]) => [id, m.uuid]),
      builds: () => buildCountRef.current,
      store: useStore,
    };

    function commitGizmo() {
      const mesh = gizmo.object as THREE.Mesh | undefined;
      if (!mesh) return;
      // ESCALA (solo cajas de boceto): mapea el factor a las COTAS de create_box
      if (gizmo.getMode() === "scale") {
        const s = mesh.scale;
        const b = mesh.userData.boxDims as { w: number; d: number; h: number } | undefined;
        const cmdId = mesh.userData.cmdId as string | undefined;
        if (b && cmdId && (Math.abs(s.x - 1) > 1e-3 || Math.abs(s.y - 1) > 1e-3 || Math.abs(s.z - 1) > 1e-3)) {
          const r2 = (v: number) => Math.round(v * 100) / 100;
          void useStore.getState().editCommand(cmdId, {
            width: r2(b.w * s.x), depth: r2(b.d * s.y), height: r2(b.h * s.z),
          }, false, true);
          const ax = axisLetter(lastAxisRef.current);
          if (ax)
            setVcb({
              mode: "scale", axis: ax, featureId: mesh.userData.featureId as string, cmdId,
              currentDim: r2((ax === "x" ? b.w * s.x : ax === "y" ? b.d * s.y : b.h * s.z)),
            });
          else setVcb(null);
        }
        return;
      }
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
      // VCB de traslación: solo si se MOVIÓ (no rotó) por un único eje
      const ax = gizmo.getMode() === "translate" && moved ? axisLetter(lastAxisRef.current) : null;
      if (ax)
        setVcb({
          mode: "translate", axis: ax, featureId: mesh.userData.featureId as string,
          committedAxisDelta: round3(ax === "x" ? dx : ax === "y" ? dy : dz),
        });
      else setVcb(null);
    }

    // Post-proceso: contorno de SELECCIÓN (silueta, estilo TinkerCad). EffectComposer con un
    // render-target MULTIMUESTREADO + HalfFloat → conserva el antialias (MSAA) y el tone-mapping
    // HDR de la escena PBR intactos (RenderPass en lineal → OutputPass aplica ACES+sRGB al final).
    // OutlinePass resalta SOLO el contorno proyectado de la pieza seleccionada (no las aristas
    // interiores que ve la cámara): remplaza el antiguo tinte emissive de selección.
    const composerRT = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 });
    const composer = new EffectComposer(renderer, composerRT);
    composer.setPixelRatio(window.devicePixelRatio);
    composer.addPass(new RenderPass(scene, camera));
    const outlinePass = new OutlinePass(new THREE.Vector2(1, 1), scene, camera);
    outlinePass.edgeStrength = 4.0;
    outlinePass.edgeGlow = 0.0;      // línea nítida, sin halo
    outlinePass.edgeThickness = 1.0;
    outlinePass.pulsePeriod = 0;     // sin parpadeo
    outlinePass.visibleEdgeColor.set(0x2ec5ff); // contorno visible: cian-azul (TinkerCad)
    outlinePass.hiddenEdgeColor.set(0x14506e);  // parte del contorno tapada por otra pieza: tenue
    composer.addPass(outlinePass);
    composer.addPass(new OutputPass());
    const selMeshes: THREE.Object3D[] = []; // buffer reusado por frame (sin asignaciones)

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = mount;
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      composer.setSize(w, h); // reajusta RTs y todos los passes (incl. OutlinePass)
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    let frame = 0;
    let dragHideHandles = false; // oculta los tiradores mientras se arrastra uno (no toca g.visible)
    // Tiradores (cuadritos + flechas): tamaño de pantalla CONSTANTE (escala ∝ distancia · sizePx) y
    // el cuadrito de ALTURA salta arriba/abajo según desde dónde mire la cámara. La VISIBILIDAD la
    // gobierna aquí (hay tiradores && no se arrastra) → reaparecen solos tras cualquier arrastre.
    const updateHandleSprites = () => {
      const g = ctx.handles;
      g.visible = g.children.length > 0 && !dragHideHandles;
      if (!g.visible) return;
      const vh = renderer.domElement.clientHeight || 1;
      const base = (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2)) / vh; // mundo por px a 1 de distancia
      const cam = camera.position;
      for (const ch of g.children) {
        const ud = ch.userData;
        // reposición dependiente de cámara ANTES de escalar (la escala usa la distancia final)
        if (ud.kind === "height") {
          ch.position.z = cam.z > (ud.minZ + ud.maxZ) / 2 ? ud.maxZ : ud.minZ;
        } else if (ud.rotFollow) { // flechas de rotación → posición Y orientación siguen a la cámara
          applyRotArrowPose(ch, ud.rotFollow, camera);
        } else if (ud.kind === "zlift") { // cono subir/bajar → ALTERNA arriba/abajo según la cámara; gap de PANTALLA constante
          const above = cam.z > (ud.topZ + ud.botZ) / 2; // cámara por encima del centro → cono ARRIBA (sube); si no → ABAJO (baja)
          const faceZ = above ? ud.topZ + ud.armZ : ud.botZ - ud.armZ; // por encima de las flechas de giro
          const dir = above ? 1 : -1;
          const d = cam.distanceTo(_zc.set(ud.cx, ud.cy, faceZ));
          ch.position.set(ud.cx, ud.cy, faceZ + dir * d * base * ud.gapPx);
          ch.rotation.set(above ? 0 : Math.PI, 0, 0); // apunta +Z (arriba) o −Z (abajo)
        }
        if (ud.sizePx) ch.scale.setScalar(cam.distanceTo(ch.position) * base * ud.sizePx * (ud.hoverScale ?? 1));
      }
    };
    // reconstruye el overlay YA (sin esperar al servidor) desde el bbox VIVO de la malla del preview →
    // cuadritos/guías/flechas/cono siguen a la caja al instante. `dimEdit` = cotas nuevas del estirón
    // (para que boxDimsFromBbox cuadre con el bbox del preview). El rebuild del servidor lo reafirma luego.
    const _pbox = new THREE.Box3();
    const rebuildOverlayFromMesh = (fid: string, dimEdit: Record<string, unknown> = {}) => {
      const mesh = ctx.meshes.get(fid);
      const feat = featuresRef.current.find((f) => f.id === fid);
      if (!mesh || !feat) return;
      mesh.updateWorldMatrix(true, false);
      _pbox.setFromObject(mesh);
      const cp = useStore.getState().scene?.document.commands.find((c) => c.id === feat.command_id)?.params ?? {};
      buildOverlay(ctx.handles, feat, [_pbox.min.x, _pbox.min.y, _pbox.min.z], [_pbox.max.x, _pbox.max.y, _pbox.max.z], { ...cp, ...dimEdit }, camera);
    };
    // TINTE de FALLO de guardado: una pieza cuyo guardado FALLÓ (y se reintenta en segundo plano) se
    // tiñe de rojizo hasta que persiste, para avisar que ese cambio aún NO está en disco. Durante el
    // guardado NORMAL (aunque tarde) NO se tiñe nada — la sincronización es silenciosa. Clona el material
    // (no muta compartidos) y se recalcula cada frame → robusto a que el rebuild reemplace la malla.
    const tinted = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>(); // malla → material original
    const applyBlockedTint = () => {
      const want = new Set<THREE.Mesh>();
      for (const id of blockedRef.current) { const mm = ctx.meshes.get(id) as THREE.Mesh | undefined; if (mm) want.add(mm); }
      for (const [mesh, orig] of tinted) { // restaura las que ya no están bloqueadas
        if (!want.has(mesh)) { (mesh.material as THREE.Material).dispose?.(); mesh.material = orig; tinted.delete(mesh); }
      }
      for (const mesh of want) { // tinta las nuevas (guardado fallido)
        if (tinted.has(mesh) || Array.isArray(mesh.material) || !mesh.material) continue;
        const orig = mesh.material;
        const clone = (orig as THREE.MeshStandardMaterial).clone();
        if (clone.emissive) { clone.emissive.setHex(0x8a2417); clone.emissiveIntensity = 1; }
        mesh.material = clone; tinted.set(mesh, orig);
      }
    };
    const animate = () => {
      frame = requestAnimationFrame(animate);
      controls.update();
      dropAnimRef.current?.tick(performance.now()); // anima las cajas del drop-test
      gravityAnimRef.current?.tick(performance.now()); // anima la caída de las mallas reales
      applyBlockedTint(); // tinte rojizo SOLO en piezas con guardado fallido (no en guardado normal)
      updateHandleSprites(); // tamaño constante de los cuadritos + altura sigue la cámara
      // contorno de selección: recolecta las mallas seleccionadas (robusto a reconstrucciones)
      selMeshes.length = 0;
      for (const id of selectionRef.current) { const m = ctx.meshes.get(id); if (m) selMeshes.push(m); }
      outlinePass.selectedObjects = selMeshes;
      composer.render(); // escena + contorno (reemplaza renderer.render)
      viewCube.render(renderer, camera); // sobre el frame ya compuesto (autoClear=false)
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

    // ---------------------------- agarrar-y-mover / estirar por caras / recuadro
    const DRAG_THRESHOLD_PX = 5; // dead-zone: hay que arrastrar > 5 px para MOVER (si no, es solo clic → seleccionar; = umbral de onClick)
    let boxStart: [number, number] | null = null;
    // `active` = ya cruzó el umbral (empezó a mover de verdad); `downXY` = px del pointerdown para medirlo.
    let movePick: { fid: string; mesh: THREE.Mesh; startPlane: THREE.Vector3; startPos: THREE.Vector3; downXY: [number, number]; active: boolean } | null = null;
    let stretchPick:
      | { kind: "corner" | "edge"; fid: string; cmdId: string; mesh: THREE.Mesh; startPos: THREE.Vector3;
          startScale: THREE.Vector3; startDims: [number, number, number]; baseZ: number; affects: StretchAffect[] }
      | { kind: "height"; fid: string; cmdId: string; mesh: THREE.Mesh; startPos: THREE.Vector3;
          startScale: THREE.Vector3; startDims: [number, number, number]; anchorZ: number }
      | { kind: "zlift"; fid: string; mesh: THREE.Mesh; startPos: THREE.Vector3; anchor: THREE.Vector3 }
      | null = null;
    let rotatePick: { fid: string; letter: "x" | "y" | "z"; mesh: THREE.Mesh; axis: THREE.Vector3;
      center: THREE.Vector3; u: THREE.Vector3; v: THREE.Vector3; radius: number; q0: THREE.Quaternion; lastAngle: number; accum: number } | null = null;
    let protractor: THREE.Mesh | null = null; // anillo-transportador (solo durante la rotación)
    const clearProtractor = () => {
      if (protractor) { protractor.geometry.dispose(); scene.remove(protractor); protractor = null; }
    };
    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 0) return; // solo izquierdo (derecho orbita, medio pan)
      if ((gizmo as unknown as { dragging?: boolean }).dragging) return;
      const st = useStore.getState();
      const posing = Object.values(st.jointValues).some((v) => v !== 0);
      const rect = renderer.domElement.getBoundingClientRect();
      const pointer = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
      // 1) ¿un TIRADOR/ANILLO de la pieza seleccionada? → estirar o rotar (prioridad sobre el cuerpo).
      // BLOQUEO: si la pieza seleccionada tiene un guardado fallido, no se manipula hasta que se guarde.
      if (handlesGroup.children.length && !e.ctrlKey && !e.metaKey && !posing && !blockedRef.current.includes(st.selection[0])) {
        const hHits = raycaster.intersectObjects(handlesGroup.children, false);
        if (hHits.length) {
          const ud = hHits[0].object.userData as
            { kind: string; letter?: "x" | "y" | "z"; axis?: number[]; affects?: StretchAffect[]; minZ?: number; maxZ?: number };
          const fid = st.selection[0];
          const mesh = fid ? ctx.meshes.get(fid) : undefined;
          const feat = featuresRef.current.find((f) => f.id === fid);
          const cmd = st.scene?.document.commands.find((c) => c.id === feat?.command_id);
          // dims EFECTIVAS (sanan cotas borradas desde el bbox → arrastre sin NaN en cajas víctimas del bug)
          const dims = (): [number, number, number] =>
            (feat && cmd && boxDimsFromBbox(feat.bbox.min, feat.bbox.max, cmd.params)) ||
            [Number(cmd!.params.width), Number(cmd!.params.depth), Number(cmd!.params.height)];
          if (mesh && feat && ud.kind === "rot" && ud.letter && ud.axis) {
            // ROTAR: snap por DISTANCIA (cerca=fino, lejos=escala); Shift = libre
            const axis = new THREE.Vector3().fromArray(ud.axis).normalize();
            const { min, max } = feat.bbox;
            const center = new THREE.Vector3((min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2);
            const radius = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2]) * 0.62 + 14; // = radio del anillo
            const { u, v } = axisBasis(axis);
            const a0 = anglePointOnAxis(center, axis, u, v, raycaster.ray);
            rotatePick = { fid, letter: ud.letter, mesh, axis, center, u, v, radius, q0: mesh.quaternion.clone(), lastAngle: a0?.angle ?? 0, accum: 0 };
            // transportador: anillo del eje activo, visible solo mientras se rota
            clearProtractor();
            protractor = new THREE.Mesh(new THREE.TorusGeometry(radius, radius * 0.028 + 1.4, 8, 72), ROT_MAT[ud.letter]);
            protractor.position.copy(center);
            protractor.quaternion.setFromUnitVectors(WORLD_Z, axis);
            protractor.renderOrder = 104;
            scene.add(protractor);
          } else if (mesh && !e.shiftKey && ud.kind === "zlift") {
            stretchPick = { kind: "zlift", fid, mesh, startPos: mesh.position.clone(), anchor: (hHits[0].object as THREE.Object3D).position.clone() };
          } else if (mesh && cmd && !e.shiftKey && (ud.kind === "corner" || ud.kind === "edge") && ud.affects) {
            const startDims = dims();
            stretchPick = {
              kind: ud.kind, fid, cmdId: cmd.id, mesh, startPos: mesh.position.clone(), startScale: mesh.scale.clone(),
              startDims, baseZ: mesh.position.z - startDims[2] / 2, affects: ud.affects,
            };
          } else if (mesh && cmd && !e.shiftKey && ud.kind === "height" && ud.minZ !== undefined && ud.maxZ !== undefined) {
            const startDims = dims();
            const above = camera.position.z > (ud.minZ + ud.maxZ) / 2;
            stretchPick = {
              kind: "height", fid, cmdId: cmd.id, mesh, startPos: mesh.position.clone(), startScale: mesh.scale.clone(),
              startDims, anchorZ: above ? ud.minZ : ud.maxZ, // ancla en la cara opuesta al icono
            };
          }
          if (stretchPick || rotatePick) {
            dragHideHandles = true;
            isDraggingObjRef.current = true;
            controls.enabled = false;
            e.preventDefault();
            return;
          }
        }
      }
      // 2) ¿un SÓLIDO? → AGARRAR y mover ; si no → RECUADRO
      const hits = raycaster.intersectObjects(group.children, false);
      if (hits.length && !e.shiftKey && !e.ctrlKey && !e.metaKey && !posing) {
        const fid = hits[0].object.userData.featureId as string;
        if (!st.selection.includes(fid)) st.select([fid]);
        if (blockedRef.current.includes(fid)) { e.preventDefault(); return; } // bloqueada (guardado fallido) → solo seleccionar
        const mesh = hits[0].object as THREE.Mesh;
        const z = hits[0].point.z;
        const startPlane = rayPlanePoint(raycaster.ray, z) ?? hits[0].point.clone();
        // PENDIENTE: aún no movemos. Solo se activa el arrastre al superar DRAG_THRESHOLD_PX (ver
        // onPointerMove) → un clic con temblor de 1-2 px solo SELECCIONA, no mueve (como TinkerCad).
        movePick = { fid, mesh, startPlane, startPos: mesh.position.clone(), downXY: [e.clientX, e.clientY], active: false };
        e.preventDefault();
      } else {
        boxStart = [e.clientX, e.clientY];
        isBoxSelectingRef.current = true;
        controls.enabled = false;
        e.preventDefault();
      }
    };
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
    const onPointerMove = (e: PointerEvent) => {
      if (!rotatePick && !stretchPick && !movePick && !boxStart) { hoverHandles(e); return; }
      if (rotatePick) { // rotar: preview girando el mesh sobre su centro (snap 22.5°, Shift=libre)
        const rp = rotatePick;
        const rect = renderer.domElement.getBoundingClientRect();
        const pointer = new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1,
        );
        raycaster.setFromCamera(pointer, camera);
        const cur = anglePointOnAxis(rp.center, rp.axis, rp.u, rp.v, raycaster.ray);
        if (cur) {
          rp.accum += shortestAngleDiff(rp.lastAngle, cur.angle);
          rp.lastAngle = cur.angle;
          const deg = snapAngleByDistance(THREE.MathUtils.radToDeg(rp.accum), cur.dist, rp.radius, e.shiftKey);
          rp.mesh.quaternion.copy(rp.q0);
          rp.mesh.rotateOnWorldAxis(rp.axis, THREE.MathUtils.degToRad(deg));
          if (liveAngleRef.current) liveAngleRef.current.textContent = `↻ ${deg.toFixed(1)}°`;
        }
        return;
      }
      if (stretchPick) { // estirar anclado a la base: preview escalando el mesh + fijando el ancla
        const rect = renderer.domElement.getBoundingClientRect();
        const pointer = new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1,
        );
        raycaster.setFromCamera(pointer, camera);
        const st = useStore.getState();
        const snap = (v: number) => (st.snapEnabled ? Math.round(v / (st.snapStep || 1)) * (st.snapStep || 1) : v);
        const sp = stretchPick;
        if (sp.kind === "corner" || sp.kind === "edge") {
          const p = rayPlanePoint(raycaster.ray, sp.baseZ); // cursor sobre el plano de la base
          if (p) {
            sp.mesh.scale.copy(sp.startScale);
            sp.mesh.position.copy(sp.startPos);
            for (const af of sp.affects) {
              const cur = af.i === 0 ? p.x : p.y;
              const newDim = Math.max(1, snap(Math.abs(cur - af.fixed)));
              sp.mesh.scale.setComponent(af.i, newDim / sp.startDims[af.i]);
              sp.mesh.position.setComponent(af.i, (cur + af.fixed) / 2);
            }
            const d = sp.startDims;
            if (liveAngleRef.current)
              liveAngleRef.current.textContent = `${Math.round(d[0] * sp.mesh.scale.x)} × ${Math.round(d[1] * sp.mesh.scale.y)} mm`;
          }
        } else if (sp.kind === "height") {
          const cz = sp.anchorZ + distanceAlongAxis(new THREE.Vector3(sp.startPos.x, sp.startPos.y, sp.anchorZ), WORLD_Z, raycaster.ray);
          const newH = Math.max(1, snap(Math.abs(cz - sp.anchorZ)));
          sp.mesh.scale.copy(sp.startScale);
          sp.mesh.scale.setComponent(2, newH / sp.startDims[2]);
          sp.mesh.position.setZ((cz + sp.anchorZ) / 2);
          if (liveAngleRef.current) liveAngleRef.current.textContent = `alto ${newH.toFixed(0)} mm`;
        } else if (sp.kind === "zlift") { // cono: mover en Z
          const dz = snap(distanceAlongAxis(sp.anchor, WORLD_Z, raycaster.ray));
          sp.mesh.position.set(sp.startPos.x, sp.startPos.y, sp.startPos.z + dz);
          if (liveAngleRef.current) liveAngleRef.current.textContent = `Z ${dz >= 0 ? "+" : ""}${dz.toFixed(1)} mm`;
        }
        return;
      }
      if (movePick) { // arrastre directo: desliza el sólido por el plano de trabajo (XY)
        if (!movePick.active) { // dead-zone: ¿ya se arrastró lo suficiente para considerarlo MOVER?
          if (Math.hypot(e.clientX - movePick.downXY[0], e.clientY - movePick.downXY[1]) < DRAG_THRESHOLD_PX) return;
          movePick.active = true; // cruzó el umbral → ahora sí arrastra (oculta tiradores, congela órbita)
          dragHideHandles = true;
          isDraggingObjRef.current = true;
          controls.enabled = false;
        }
        const rect = renderer.domElement.getBoundingClientRect();
        const pointer = new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1,
        );
        raycaster.setFromCamera(pointer, camera);
        const now = rayPlanePoint(raycaster.ray, movePick.startPlane.z);
        if (now) {
          const dx = now.x - movePick.startPlane.x;
          const dy = now.y - movePick.startPlane.y;
          movePick.mesh.position.set(movePick.startPos.x + dx, movePick.startPos.y + dy, movePick.startPos.z);
          if (liveAngleRef.current) liveAngleRef.current.textContent = `Δ ${dx.toFixed(1)}, ${dy.toFixed(1)} mm`;
        }
        return;
      }
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
      if (rotatePick) { // fin del giro → commit transform{rotate} (rota sobre el centro del bbox)
        const rp = rotatePick;
        rotatePick = null;
        clearProtractor();
        dragHideHandles = false; // reaparecen al soltar
        isDraggingObjRef.current = false;
        controls.enabled = !(gizmo as unknown as { dragging?: boolean }).dragging;
        if (liveAngleRef.current) liveAngleRef.current.textContent = "";
        const rect = renderer.domElement.getBoundingClientRect();
        const pointer = new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1,
        );
        raycaster.setFromCamera(pointer, camera);
        const cur = anglePointOnAxis(rp.center, rp.axis, rp.u, rp.v, raycaster.ray);
        let deg = snapAngleByDistance(THREE.MathUtils.radToDeg(rp.accum), cur?.dist ?? rp.radius, rp.radius, e.shiftKey);
        deg = Math.round(deg * 10) / 10;
        if (Math.abs(deg) > 0.05) {
          // OPTIMISTA: fija el preview al valor commiteado y DÉJALO (sin snap-back); el rebuild lo reemplaza sin salto.
          rp.mesh.quaternion.copy(rp.q0);
          rp.mesh.rotateOnWorldAxis(rp.axis, THREE.MathUtils.degToRad(deg));
          void useStore.getState().runCommandSilent("transform", {
            feature: rp.fid,
            rotate: { x: rp.letter === "x" ? deg : 0, y: rp.letter === "y" ? deg : 0, z: rp.letter === "z" ? deg : 0 },
          });
          rebuildOverlayFromMesh(rp.fid); // reubica las flechas al instante (caja rotada → sin cuadritos)
        } else {
          rp.mesh.quaternion.copy(rp.q0); // no giró → restaura
        }
        return;
      }
      if (stretchPick) { // fin del estirón → commit paramétrico (o restaura si no cambió)
        const sp = stretchPick;
        stretchPick = null;
        dragHideHandles = false; // reaparecen al soltar (el rebuild los recoloca)
        isDraggingObjRef.current = false;
        controls.enabled = !(gizmo as unknown as { dragging?: boolean }).dragging;
        if (liveAngleRef.current) liveAngleRef.current.textContent = "";
        const rect = renderer.domElement.getBoundingClientRect();
        const pointer = new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1,
        );
        raycaster.setFromCamera(pointer, camera);
        const st = useStore.getState();
        const snap = (v: number) => (st.snapEnabled ? Math.round(v / (st.snapStep || 1)) * (st.snapStep || 1) : v);
        const r2 = (v: number) => Math.round(v * 100) / 100;
        // OPTIMISTA: el preview arrastrado SE QUEDA (sin snap-back); el rebuild trae la geometría real
        // y hace el swap sin salto. Solo se restaura si NO hubo cambio.
        const restore = () => { if (sp.kind !== "zlift") sp.mesh.scale.copy(sp.startScale); sp.mesh.position.copy(sp.startPos); };
        // `position` del comando ≠ centro en MUNDO: los `transform` del log (arrastres previos) se re-aplican
        // ENCIMA en cada regenerate → el commit debe ser params.position + delta, NUNCA el centro de mundo.
        // La base sale de la última edición ENCOLADA si existe (st.scene se retrasa por el coalescing en
        // estirones rápidos — anclar a la escena vieja hacía derivar la caja), y si no, de la escena.
        const basePos = (id: string) => {
          const q = (queuedEditParams(id)?.position ??
            st.scene?.document.commands.find((c) => c.id === id)?.params.position) as { x?: number; y?: number; z?: number } | undefined;
          return { x: q?.x ?? 0, y: q?.y ?? 0, z: q?.z ?? 0 };
        };
        if (sp.kind === "corner" || sp.kind === "edge") {
          const p = rayPlanePoint(raycaster.ray, sp.baseZ);
          if (!p) { restore(); return; }
          const edit: Record<string, unknown> = {};
          const t = { x: 0, y: 0, z: 0 };
          let changed = false;
          for (const af of sp.affects) {
            const cur = af.i === 0 ? p.x : p.y;
            const newDim = Math.max(1, r2(snap(Math.abs(cur - af.fixed))));
            if (Math.abs(newDim - sp.startDims[af.i]) > 0.1) changed = true;
            edit[af.dim] = newDim;
            (t as Record<string, number>)[af.i === 0 ? "x" : "y"] = (cur + af.fixed) / 2 - sp.startPos.getComponent(af.i);
          }
          if (!changed) { restore(); return; }
          // ATÓMICO: cotas + posición (para fijar el ancla) en UN solo editCommand → 1 regeneración, sin comando transform extra
          const bp = basePos(sp.cmdId);
          edit.position = { x: r2(bp.x + t.x), y: r2(bp.y + t.y), z: r2(bp.z + t.z) };
          void st.editCommandSilent(sp.cmdId, edit, true); // guardado silencioso + coalescing (último gana)
          rebuildOverlayFromMesh(sp.fid, edit); // overlay al instante (no espera al servidor)
        } else if (sp.kind === "height") {
          const cz = sp.anchorZ + distanceAlongAxis(new THREE.Vector3(sp.startPos.x, sp.startPos.y, sp.anchorZ), WORLD_Z, raycaster.ray);
          const newH = Math.max(1, r2(snap(Math.abs(cz - sp.anchorZ))));
          if (Math.abs(newH - sp.startDims[2]) <= 0.1) { restore(); return; }
          const dzc = (cz + sp.anchorZ) / 2 - sp.startPos.z;
          const bp = basePos(sp.cmdId);
          void st.editCommandSilent(sp.cmdId, { height: newH, position: { x: r2(bp.x), y: r2(bp.y), z: r2(bp.z + dzc) } }, true);
          rebuildOverlayFromMesh(sp.fid, { height: newH });
        } else if (sp.kind === "zlift") {
          const dz = snap(distanceAlongAxis(sp.anchor, WORLD_Z, raycaster.ray));
          if (Math.abs(dz) <= 0.1) { restore(); return; }
          void st.runCommandSilent("transform", { feature: sp.fid, translate: { x: 0, y: 0, z: Math.round(dz * 1000) / 1000 } });
          rebuildOverlayFromMesh(sp.fid);
        }
        return;
      }
      if (movePick) { // fin del arrastre directo → commit del movimiento (o restaura si no movió)
        const mp = movePick;
        movePick = null;
        if (!mp.active) return; // nunca cruzó el umbral → fue solo un CLIC: ya seleccionó, no mover ni comitear
        dragHideHandles = false; // reaparecen al soltar
        isDraggingObjRef.current = false;
        controls.enabled = !(gizmo as unknown as { dragging?: boolean }).dragging;
        if (liveAngleRef.current) liveAngleRef.current.textContent = "";
        const dx = mp.mesh.position.x - mp.startPos.x;
        const dy = mp.mesh.position.y - mp.startPos.y;
        if (Math.hypot(dx, dy) > 1e-2) {
          const r3 = (v: number) => Math.round(v * 1000) / 1000;
          void useStore.getState().runCommandSilent("transform", { feature: mp.fid, translate: { x: r3(dx), y: r3(dy), z: 0 } });
          rebuildOverlayFromMesh(mp.fid); // overlay sigue a la pieza al instante
        } else {
          mp.mesh.position.copy(mp.startPos); // no movió → deja el mesh donde estaba
        }
        return;
      }
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
    const onFitEvent = (ev: Event) => {
      const id = (ev as CustomEvent).detail?.id as string | undefined;
      const mesh = id ? ctx.meshes.get(id) : null;
      if (mesh) frameBox(new THREE.Box3().setFromObject(mesh));
      else fitTo();
    };
    renderer.domElement.addEventListener("contextmenu", onContext);
    renderer.domElement.addEventListener("dblclick", onDblClick);
    window.addEventListener("apolo:fit", onFitEvent as EventListener);
    const disposeGltfExport = installGltfExport(
      group, () => useStore.getState().scene?.document.name ?? "modelo",
    );
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
      window.removeEventListener("keydown", onModKey);
      window.removeEventListener("keyup", onModKey);
      window.removeEventListener("apolo:fit", onFitEvent as EventListener);
      snapMarker.geometry.dispose();
      (snapMarker.material as THREE.Material).dispose();
      clearProtractor();
      disposeGltfExport();
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
      outlinePass.dispose();
      composer.dispose(); // libera sus render-targets (incl. composerRT)
      renderer.dispose();
      mount.removeChild(renderer.domElement);
      ctxRef.current = null;
    };
  }, []);

  // -------------------------------- reconstruir mallas (diff persistente, V6.2b)
  // En vez de tirar y reconstruir TODAS las mallas en cada cambio de escena, se diffea por
  // fid usando `rev` (revisión de geometría del server): solo la pieza cuyo shape cambió se
  // reconstruye; las demás conservan su malla three.js (lo caro es teselar + aristas). Un
  // metadato de apariencia (color/material/guía) rehace solo el material. Shading/sección/
  // catálogo cambian el material/recorte de TODAS → rebuild total (como antes).
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    ctx.gizmo.detach();
    const planes = sectionPlanes(sectionAxis, sectionPos, features);
    const catalogByRef = new Map(catalog.map((c) => [c.ref, c]));
    const built = builtRef.current;
    const shared = sharedRef.current;

    // Invalidación TOTAL: los planos de sección dependen del bbox del modelo (cambian al
    // editar con sección activa) → su firma entra en la clave; shading/catálogo también.
    const planeSig = planes
      .map((p) => `${p.normal.x},${p.normal.y},${p.normal.z},${p.constant.toFixed(2)}`)
      .join(";");
    const buildKey = `${shading}|${planeSig}|${catalog.length}`;
    if (buildKey !== buildKeyRef.current) {
      for (const e of built.values()) disposeMesh(e.mesh);
      ctx.group.clear();
      ctx.meshes.clear();
      built.clear();
      for (const g of shared.values()) disposeSharedGeom(g);
      shared.clear();
      buildKeyRef.current = buildKey;
    }

    // 1) (re)construir lo nuevo o de rev distinto; actualizar apariencia en sitio el resto
    const desired = new Set<string>();
    for (const feat of features) {
      if (!feat.visible) continue;
      desired.add(feat.id);
      const rev = feat.rev ?? 0;
      const app = appearanceSig(feat);
      const prev = built.get(feat.id);
      if (prev && prev.rev === rev) {
        if (prev.app !== app) {
          applyAppearance(prev.mesh, feat, shading, planes, catalogByRef);
          prev.app = app;
        }
        continue; // geometría REUSADA (lo caro no se repite)
      }
      if (prev) { ctx.group.remove(prev.mesh); disposeMesh(prev.mesh); }
      const mesh = buildMesh(feat, shading, planes, definitions, shared, catalogByRef);
      buildCountRef.current++;
      ctx.meshes.set(feat.id, mesh);
      ctx.group.add(mesh);
      built.set(feat.id, { rev, mesh, app, key: feat.mesh_key });
    }
    // 2) quitar mallas de fids desaparecidos o que se ocultaron
    for (const [fid, e] of [...built]) {
      if (!desired.has(fid)) {
        ctx.group.remove(e.mesh);
        disposeMesh(e.mesh);
        built.delete(fid);
        ctx.meshes.delete(fid);
      }
    }
    // 3) podar geometrías de instancia que ya ninguna malla usa
    const usedKeys = new Set<string>();
    for (const e of built.values()) if (e.key) usedKeys.add(e.key);
    for (const [k, g] of [...shared]) {
      if (!usedKeys.has(k)) { disposeSharedGeom(g); shared.delete(k); }
    }

    applyKinematicPoses(ctx.meshes, kinJoints, jointValues);
    attachGizmo(ctx, selection, gizmoMode, jointValues);
    updateGround(ctx.ground, ctx.dir, new THREE.Box3().setFromObject(ctx.group));
  }, [features, definitions, shading, sectionAxis, sectionPos, catalog]);

  // ------------------------------------------------------ selección y gizmo
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
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
    isBusy: () => isGizmoDraggingRef.current || isBoxSelectingRef.current || isDraggingObjRef.current,
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

  // snap de traslación a rejilla (Boceto · Fase 2): fallback nativo cuando la inferencia a
  // puntos no acierta. La inferencia a puntos y el snap dimensional de escala viven en el
  // handler objectChange del gizmo (leen snapEnabled/snapStep de la store en vivo).
  useEffect(() => {
    ctxRef.current?.gizmo.setTranslationSnap(snapEnabled ? snapStep : null);
  }, [snapEnabled, snapStep]);

  // F4B/F4C: overlay de la pieza seleccionada — 3 ANILLOS de rotación (cualquier sólido) +
  // TIRADORES de cara/cono Z (solo create_box no instanciada y ALINEADA). Se recolocan al
  // cambiar selección/features (tras cada commit el bbox sale fresco). Ocultos durante el
  // arrastre (los repone el pointerup/rebuild).
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    const feat = selection.length === 1 ? features.find((f) => f.id === selection[0]) : undefined;
    const cmd = feat ? useStore.getState().scene?.document.commands.find((c) => c.id === feat.command_id) : undefined;
    buildOverlay(ctx.handles, feat, feat?.bbox.min ?? [], feat?.bbox.max ?? [], cmd?.params ?? {}, ctx.camera);
  }, [selection, features]);

  // VCB: aplica el valor EXACTO tecleado sobre el eje del último arrastre.
  const applyVcb = (raw: number) => {
    const v = vcbRef.current;
    setVcb(null);
    if (!v || !Number.isFinite(raw)) return;
    if (v.mode === "translate") {
      const corr = raw - v.committedAxisDelta; // residual sobre lo que ya movió el arrastre
      if (Math.abs(corr) < 1e-4) return;
      const t = { x: 0, y: 0, z: 0 };
      t[v.axis] = Math.round(corr * 1000) / 1000;
      void useStore.getState().runCommand("transform", { feature: v.featureId, translate: t });
    } else {
      if (!(raw > 0)) return;
      const key = v.axis === "x" ? "width" : v.axis === "y" ? "depth" : "height";
      const r2 = Math.round(raw * 100) / 100;
      if (r2 !== v.currentDim) void useStore.getState().editCommand(v.cmdId, { [key]: r2 }, false, true);
    }
  };

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

  // escala paramétrica: solo una caja (create_box) no instanciada — mapea a sus cotas
  const scaleFeat = selection.length === 1 ? features.find((f) => f.id === selection[0]) : undefined;
  const canScale = !!scaleFeat && scaleFeat.command_type === "create_box" && !scaleFeat.mesh_key;
  useEffect(() => {
    if (gizmoMode === "scale" && !canScale) setGizmoMode("off");
  }, [gizmoMode, canScale]);

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
        <button
          className={gizmoMode === "scale" ? "active" : ""}
          title={canScale ? "Arrastra el gizmo para redimensionar la caja de boceto" : "Escalar solo aplica a una caja de boceto"}
          disabled={!canScale}
          onClick={() => setGizmoMode(gizmoMode === "scale" ? "off" : "scale")}
        >
          Escalar
        </button>
        <button
          className={snapEnabled ? "active" : ""}
          title={
            snapEnabled
              ? `Snap ON (rejilla ${snapStep} mm + puntos de otras piezas). Mantén Ctrl al arrastrar para soltarlo`
              : "Snap OFF (arrastre libre)"
          }
          onClick={toggleSnap}
        >
          🧲 Snap{snapEnabled ? ` ${snapStep}` : " off"}
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
      {selection.length > 0 && !picking && (
        <div className="selection-bar">
          <span className="sb-count">{selName || `${selection.length} sólidos`}</span>
          <span className="overlay-sep" />
          <button title="Duplicar (Ctrl+D)" onClick={() => void useStore.getState().duplicateSelection()}>
            <Copy size={15} />
          </button>
          <button title="Ocultar (H)" onClick={() => void useStore.getState().hideSelection()}>
            <EyeOff size={15} />
          </button>
          <button title="Aislar (I)" onClick={() => void useStore.getState().isolate()}>
            <Focus size={15} />
          </button>
          <button title="Centrar (F)" onClick={fitTo}>
            <Crop size={15} />
          </button>
          <span className="overlay-sep" />
          <button className="danger" title="Eliminar (Supr)" onClick={() => void useStore.getState().deleteSelection()}>
            <Trash2 size={15} />
          </button>
        </div>
      )}
      <div className="viewport-status">
        mm · {features.filter((f) => f.visible).length} sólidos
        {selName ? ` · selección: ${selName}` : ""}
        {selExtent ? ` · ${selExtent}` : ""}
        <span ref={liveAngleRef} className="live-angle" />
        {vcb && (
          <span className="vcb" style={{ pointerEvents: "auto", marginLeft: 8 }}>
            {vcb.mode === "translate" ? `Δ${vcb.axis.toUpperCase()} = ` : `${vcb.axis.toUpperCase()} = `}
            <input
              autoFocus
              type="number"
              defaultValue={vcb.mode === "translate" ? vcb.committedAxisDelta : vcb.currentDim}
              onFocus={(e) => e.target.select()}
              onKeyDown={(e) => {
                if (e.key === "Enter") applyVcb(Number((e.target as HTMLInputElement).value));
                else if (e.key === "Escape") setVcb(null);
              }}
              style={{ width: 74 }}
              title="Teclea el valor exacto de este eje y pulsa Enter"
            />{" "}
            mm
          </span>
        )}
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
  // modo escala: guarda en la malla las cotas base + el comando (create_box) → commitGizmo
  // mapea el factor de escala a width/depth/height del comando
  if (mode === "scale") {
    const st = useStore.getState();
    const feat = st.scene?.features.find((f) => f.id === selection[0]);
    const cmd = st.scene?.document.commands.find((c) => c.id === feat?.command_id);
    if (cmd?.type === "create_box") {
      mesh.userData.cmdId = cmd.id;
      mesh.userData.boxDims = {
        w: Number(cmd.params.width), d: Number(cmd.params.depth), h: Number(cmd.params.height),
      };
    }
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
