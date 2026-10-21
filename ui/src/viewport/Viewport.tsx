import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { selectFeatures, useStore } from "../state/store";
import type { Shading, SharedGeom } from "./meshes";
import { updateGround } from "./scene-setup";
import { buildProductMeshes, createDropAnimator, disposeProducts, type DropAnimator } from "./products";
import { createGravityAnimator, type GravityAnimator } from "./gravity";
import { installShortcuts, type ShortcutHandlers } from "./shortcuts";
import Spinner from "../ui/Spinner";
import BarraVista, { type GizmoMode, type SectionAxis } from "./BarraVista";
import PanelRotar from "./PanelRotar";
import BarraSeleccion from "./BarraSeleccion";
import EstadoViewport, { type Vcb } from "./EstadoViewport";
import { ACERCAR, ALEJAR, cajaDe, dolly, encuadrar, VIEWS } from "./camara";
import { useVisor } from "../visor/estado";
import { crearPipeline } from "./pipeline";
import { actualizarTiradores, buildOverlay } from "./gizmoRot";
import { applyKinematicPoses, attachGizmo, sectionPlanes } from "./poses";
import { sincronizarMallas, type MallaConstruida } from "./mallas";
import { objetoMedida } from "./medicion";
import { crearTinteBloqueo } from "./tinteBloqueo";
import { crearSombraContacto } from "./sombraContacto";
import type { CtxInteraccion, VistaCtx } from "./interaccion/ctx";
import { aplicarVcb, instalarGizmo } from "./interaccion/gizmo";
import { instalarSeleccion } from "./interaccion/seleccion";
import { instalarManipulacion } from "./interaccion/manipular";
import { instalarErgonomia } from "./interaccion/ergonomia";
import type { Reproductor } from "./marcha/reproductor";
import { useMarchaEnVista } from "./marcha/enVista";
import BarraMarcha from "./marcha/BarraMarcha";
import { crearGrabacionVista } from "./grabacion/enVista";
import { crearGrabacionGuion } from "./grabacion/guionVista";
import { registrarGrabador } from "./grabacion/registro";
import { crearFotoRealista, registrarFoto } from "./grabacion/trazado/foto";

/* Orquestador del viewport: estado de React, efectos que sincronizan la escena con la store y
   el JSX de las barras. El render vive en `pipeline.ts` (renderer, composer, bucle); la
   interacción, en `interaccion/` (cada módulo `instalarX(ctx) → limpieza` con un `Ctx`
   explícito); el overlay del gizmo, en `gizmoRot.ts`; sección y cinemática, en `poses.ts`; el
   diff de mallas, en `mallas.ts` (plan piso-con-sombra, D1). */
export default function Viewport() {
  const mountRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const ctxRef = useRef<VistaCtx | null>(null);

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
  const visor = useVisor((s) => s.modo === "visor");
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
  const marchaRef = useRef<Reproductor | null>(null); // la máquina en marcha (visor-realista D4)
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
  const builtRef = useRef<Map<string, MallaConstruida>>(new Map());
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
    const pipe = crearPipeline(mount, () => selectionRef.current);
    const { scene, camera, controls, gizmo, renderer, group, meshes, dir, ground } = pipe;
    const handlesGroup = new THREE.Group(); // tiradores de la caja seleccionada (F4B)
    scene.add(handlesGroup);
    const sombra = crearSombraContacto(renderer, scene, group, ground); // la máquina se apoya en el piso
    const ctx: VistaCtx = { scene, camera, controls, gizmo, renderer, group, meshes, dir, ground, handles: handlesGroup, sombra };
    ctxRef.current = ctx;
    // ctx fresco → resetea el diff de mallas (V6.2b): builtRef apuntaba al group anterior
    builtRef.current.clear();
    sharedRef.current.clear();
    buildKeyRef.current = "";
    // hook de depuración/E2E (V6.2b): identidad de mallas + contador de builds para
    // verificar el reuso sin depender del screenshot (que se cuelga por el rAF).
    const ocultarAlGrabar = () => [handlesGroup, ...(measureObjRef.current ? [measureObjRef.current] : [])];
    // el guion del video (video-realista F3): el botón «Grabar video» y `?grabar=<sesion>`
    const grabarSesion = crearGrabacionGuion({ pipe, sombra, marcha: () => marchaRef.current, ocultar: ocultarAlGrabar });
    const fotoRealista = crearFotoRealista(pipe, ocultarAlGrabar); // trazado de rayos (video-realista F4)
    (window as unknown as { __apolo?: unknown }).__apolo = {
      meshIds: () => [...ctx.meshes].map(([id, m]) => [id, m.uuid]),
      builds: () => buildCountRef.current,
      sombraRecalculos: () => sombra.recalculos(), // en reposo no sube (piso-con-sombra, D3)
      store: useStore,
      grabar: crearGrabacionVista(pipe, ocultarAlGrabar), // el giro con la marcha (video-realista F2)
      grabarSesion,
      fotoRealista,
    };
    const ci: CtxInteraccion = {
      ...ctx, mount, viewCube: pipe.viewCube, raycaster: new THREE.Raycaster(), boxRef, liveAngleRef,
      featuresRef, blockedRef, lastAxisRef, isGizmoDraggingRef, isBoxSelectingRef, isDraggingObjRef,
      ocultarTiradores: { current: false }, setVcb, setViewDir, frameBox, fitTo,
    };
    const limpiezas = [instalarGizmo(ci), registrarGrabador(grabarSesion), registrarFoto(fotoRealista)];

    // `ahora` = el reloj del cuadro: el real, o el virtual al grabar (video-realista D3)
    pipe.antesDeComponer((ahora) => dropAnimRef.current?.tick(ahora)); // cajas del drop-test
    pipe.antesDeComponer((ahora) => gravityAnimRef.current?.tick(ahora)); // caída de las mallas reales
    pipe.antesDeComponer((ahora) => marchaRef.current?.tick(ahora)); // la marcha simulada
    pipe.antesDeComponer(crearTinteBloqueo(ctx.meshes, blockedRef)); // rojizo SÓLO con guardado fallido
    // tamaño constante de los cuadritos + altura sigue la cámara
    pipe.antesDeComponer(() => actualizarTiradores(ctx.handles, camera, renderer.domElement, ci.ocultarTiradores.current));
    // sombra de contacto: sólo si quedó sucia; mientras algo se arrastra o cae, ≤ 10 Hz
    pipe.antesDeComponer((ahora) => sombra.actualizar(ahora,
      isDraggingObjRef.current || isGizmoDraggingRef.current || useStore.getState().gravityPlaying));
    pipe.arrancar();

    limpiezas.push(instalarSeleccion(ci), instalarManipulacion(ci), instalarErgonomia(ci));
    return () => {
      pipe.detener();
      for (const limpiar of limpiezas) limpiar();
      dropAnimRef.current = null;
      gravityAnimRef.current = null;
      gravityRestoreRef.current?.();
      gravityRestoreRef.current = null;
      if (productsGroupRef.current) {
        disposeProducts(productsGroupRef.current);
        scene.remove(productsGroupRef.current);
        productsGroupRef.current = null;
      }
      sombra.dispose();
      pipe.dispose();
      ctxRef.current = null;
    };
  }, []);

  // -------------------------------- reconstruir mallas (diff persistente, V6.2b, `mallas.ts`)
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    ctx.gizmo.detach();
    const planes = sectionPlanes(sectionAxis, sectionPos, features);
    sincronizarMallas(ctx, { builtRef, sharedRef, buildKeyRef, buildCountRef }, features, definitions, shading, planes, catalog);
    ctx.sombra.fijarPlanos(planes); // mallas, visibilidad o sección cambiaron → sombra sucia
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
    ctx.sombra.marcarSucia();
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
    const group = objetoMedida(measure);
    ctx.scene.add(group);
    measureObjRef.current = group;
  }, [measure]);

  // -------------------------------------------- física: cajas del drop-test
  // Overlay efímero (patrón medición). Las cajas van a ctx.scene (NO a ctx.group)
  // → fuera del raycast de selección/box-select. El animador las mueve en el rAF.
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    ctx.sombra.marcarSucia();
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
    ctx.sombra.marcarSucia(); // la caída mueve las mallas reales (mientras corre, la marca el bucle)
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

  // la marcha simulada: después de mallas y pose cinemática (se arma sobre las mallas nuevas)
  useMarchaEnVista(ctxRef, marchaRef, features, kinJoints, jointValues, projectId);

  const startMeasure = () => {
    setMeasure(null);
    const store = useStore.getState();
    store.requestPick((p1) => {
      useStore.getState().requestPick((p2) => setMeasure({ p1: [...p1], p2: [...p2] }));
    });
  };

  // Encuadra una caja: mantiene la dirección actual de la cámara salvo que se dé `dir`.
  const frameBox = (box: THREE.Box3, dir?: [number, number, number]) => {
    const ctx = ctxRef.current;
    if (ctx) encuadrar(ctx.camera, ctx.controls, box, dir);
  };
  const selectionBox = (): THREE.Box3 | null => {
    const ctx = ctxRef.current;
    return ctx ? cajaDe(ctx.meshes, selectionRef.current) : null;
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
  const zoom = (factor: number) => { // Acercar / Alejar del visor
    const ctx = ctxRef.current;
    if (!ctx) return;
    dolly(ctx.camera.position, ctx.controls.target, factor);
    ctx.controls.update();
  };

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
    aplicarVcb(v, raw);
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
      <BarraVista
        visor={visor}
        encuadrar={fitTo}
        acercar={() => zoom(ACERCAR)}
        alejar={() => zoom(ALEJAR)}
        vistas={Object.keys(VIEWS)}
        setView={setView}
        shading={shading}
        setShading={setShading}
        gizmoMode={gizmoMode}
        setGizmoMode={setGizmoMode}
        canScale={canScale}
        snapEnabled={snapEnabled}
        snapStep={snapStep}
        toggleSnap={toggleSnap}
        hayMedida={!!measure}
        picking={picking}
        toggleMeasure={() => (measure ? setMeasure(null) : startMeasure())}
        sectionAxis={sectionAxis}
        setSectionAxis={setSectionAxis}
        sectionPos={sectionPos}
        setSectionPos={setSectionPos}
      />
      {gizmoMode === "rotate" && (
        <PanelRotar
          rotAxis={rotAxis}
          setRotAxis={setRotAxis}
          unaPieza={selection.length === 1}
          applyRotate={applyRotate}
          rotInput={rotInput}
          setRotInput={setRotInput}
          snapDeg={snapDeg}
          setSnapDeg={setSnapDeg}
        />
      )}
      {selection.length > 0 && !picking && (
        <BarraSeleccion nombre={selName} cantidad={selection.length} ids={selection} onCentrar={fitTo} visor={visor} />
      )}
      <BarraMarcha />
      <EstadoViewport
        features={features} selection={selection} selName={selName} liveAngleRef={liveAngleRef}
        vcb={vcb} setVcb={setVcb} applyVcb={applyVcb} gizmoMode={gizmoMode} measure={measure}
      />
    </div>
  );
}
