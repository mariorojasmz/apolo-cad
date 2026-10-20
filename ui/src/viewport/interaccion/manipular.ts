import * as THREE from "three";
import { queuedEditParams, useStore } from "../../state/store";
import { distanceAlongAxis, rayPlanePoint } from "../pushpull";
import { anglePointOnAxis, axisBasis, boxDimsFromBbox, shortestAngleDiff, snapAngleByDistance, type StretchAffect } from "../handles";
import { buildOverlay, ROT_MAT, WORLD_Z } from "../gizmoRot";
import { crearHoverTiradores } from "./hoverTiradores";
import type { CtxInteraccion } from "./ctx";

/* Manipulación directa con el botón izquierdo: agarrar-y-mover un sólido, estirar una caja por
   sus tiradores, rotar por las flechas, subir/bajar con el cono y el recuadro de selección.
   Salió de Viewport.tsx sin cambiar la lógica (plan piso-con-sombra, F1). */

export function instalarManipulacion(ctx: CtxInteraccion): () => void {
  const {
    scene, camera, controls, gizmo, renderer, group, raycaster, mount, boxRef, liveAngleRef,
    featuresRef, blockedRef, isBoxSelectingRef, isDraggingObjRef, ocultarTiradores,
  } = ctx;
  const handlesGroup = ctx.handles;
  const hoverHandles = crearHoverTiradores(ctx);
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
          ocultarTiradores.current = true;
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
        ocultarTiradores.current = true;
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
      ocultarTiradores.current = false; // reaparecen al soltar
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
      ocultarTiradores.current = false; // reaparecen al soltar (el rebuild los recoloca)
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
      ocultarTiradores.current = false; // reaparecen al soltar
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

  renderer.domElement.addEventListener("pointerdown", onPointerDown);
  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
  return () => {
    renderer.domElement.removeEventListener("pointerdown", onPointerDown);
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    clearProtractor();
  };
}
