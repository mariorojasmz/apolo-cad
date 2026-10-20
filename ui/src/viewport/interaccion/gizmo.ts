import * as THREE from "three";
import { useStore } from "../../state/store";
import { buildSnapIndex, movingOffsets, nearestScreenSnap, type SnapPoint } from "../snap";
import type { Vcb } from "../EstadoViewport";
import type { CtxInteraccion } from "./ctx";

/* El gizmo de transformación (TransformControls): snapping al arrastrar (rejilla, puntos de
   otras piezas, cota de la escala), HUD en vivo y el commit al soltar, más la caja de valor
   exacto (VCB). Salió de Viewport.tsx sin cambiar la lógica (plan piso-con-sombra, F1). */

/** Eje del gizmo ("X"/"Y"/"Z") a minúscula; null si es un plano/ambiguo (sin VCB). */
export function axisLetter(a: string | null): "x" | "y" | "z" | null {
  return a === "X" ? "x" : a === "Y" ? "y" : a === "Z" ? "z" : null;
}

/** Instala los listeners del gizmo; devuelve su limpieza. Los del propio gizmo
   (`dragging-changed`, `objectChange`) no se quitan: los libera `gizmo.dispose()`. */
export function instalarGizmo(ctx: CtxInteraccion): () => void {
  const { scene, camera, controls, gizmo, renderer, featuresRef, isGizmoDraggingRef, liveAngleRef, lastAxisRef, setVcb } = ctx;

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

  return () => {
    window.removeEventListener("keydown", onModKey);
    window.removeEventListener("keyup", onModKey);
    snapMarker.geometry.dispose();
    (snapMarker.material as THREE.Material).dispose();
  };
}

/** VCB: aplica el valor EXACTO tecleado sobre el eje del último arrastre. */
export function aplicarVcb(v: Vcb, raw: number): void {
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
}
