import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { baseHandles, boxDimsFromBbox, heightHandlePos, ROT_CANDIDATES, rotArrowPlacement, zLiftPoint } from "./handles";
import { makeHandleSprite, squareDarkTex, squareLightTex } from "./handleSprites";

/* Overlay de la pieza seleccionada: flechas de rotación (geometría, materiales y pose que sigue
   a la cámara), tiradores de estirón, cono de subir/bajar y líneas guía. Salió de Viewport.tsx
   sin cambiar la lógica (plan piso-con-sombra, F1). */

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
export const WORLD_Z = new THREE.Vector3(0, 0, 1);
const _camRight = new THREE.Vector3(); // scratch: "derecha" de la cámara
const _dRot = new THREE.Vector3(), _yAxis = new THREE.Vector3(), _axisV = new THREE.Vector3(), _mtx = new THREE.Matrix4();
const _zc = new THREE.Vector3(); // scratch: centro-top para el gap del cono Z-lift

/** Coloca UNA flecha de rotación que SIGUE a la cámara. Dos modos:
   - `perp` (azul): arco ⟂ al eje, anclado en la cara lateral ⟂ eje más a la derecha de la cámara
     (patrón `rotArrowPlacement`), a la base.
   - `coplanar` (rojo/verde): arco COPLANAR con la cara del PROPIO eje (⟂ eje = plano de la cara),
     en la cara que MIRA a la cámara, elevado al top; se orienta con la derecha de la cámara
     proyectada a ese plano (+ `tilt`). Evita la degeneración de `perp` cuando la cara ∥ al eje. */
export function applyRotArrowPose(mesh: THREE.Object3D, rf: RotFollow, camera: THREE.PerspectiveCamera): void {
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
export interface RotFollow { min: number[]; max: number[]; axis: "x" | "y" | "z"; m: number; zFrac: number; tilt: number; mode: "perp" | "coplanar"; side?: "face" | "back" | "left" | "right"; inset?: number; candidates?: [number, number, number][]; }
// Anillos de rotación (F4C): color por eje (X rojo / Y verde / Z azul). Geometría por selección
// (radio del bbox) → se dispone al limpiar; los materiales se comparten.
export const ROT_MAT: Record<"x" | "y" | "z", THREE.MeshBasicMaterial> = {
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
export function buildOverlay(
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

/** Por frame: tamaño de pantalla CONSTANTE de los tiradores (escala ∝ distancia · sizePx) y el
   cuadrito de ALTURA salta arriba/abajo según desde dónde mire la cámara. La VISIBILIDAD la
   gobierna aquí (hay tiradores && no se arrastra) → reaparecen solos tras cualquier arrastre.
   `ocultar` = se está arrastrando un tirador. */
export function actualizarTiradores(
  g: THREE.Group, camera: THREE.PerspectiveCamera, canvas: { clientHeight: number }, ocultar: boolean,
): void {
  g.visible = g.children.length > 0 && !ocultar;
  if (!g.visible) return;
  const vh = canvas.clientHeight || 1;
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
}
