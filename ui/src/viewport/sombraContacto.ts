import * as THREE from "three";
import { HorizontalBlurShader } from "three/examples/jsm/shaders/HorizontalBlurShader.js";
import { VerticalBlurShader } from "three/examples/jsm/shaders/VerticalBlurShader.js";
import { FullScreenQuad } from "three/examples/jsm/postprocessing/Pass.js";

/* Sombra de CONTACTO bajo la máquina (plan piso-con-sombra, D2–D5): sin ella la máquina parece
   flotar sobre el fondo. Técnica del ejemplo `webgl_shadow_contact` de three.js (MIT): una cámara
   ORTOGRÁFICA en el piso mira hacia arriba, dibuja la PROFUNDIDAD de las piezas a un render target
   chico (lo cercano al piso, oscuro; lo alto, claro; más arriba del alcance, nada), lo desenfoca
   en horizontal + vertical y un plano en el piso muestra esa textura.

   No es un pase del composer: es una textura que se calcula aparte, en la tarea «antes de
   componer» del bucle (`pipeline.ts`), y SÓLO cuando algo cambió (bandera `sucia`, D3): en reposo
   cuesta cero, y durante un arrastre o una animación se recalcula como mucho a 10 Hz. La sombra
   direccional sigue (D4) para la sombra propia; el plano se muestra sólo si se muestra el suelo
   (D5) y, como mira hacia arriba, desde abajo no se ve. */

/** Lado del render target de la profundidad (px). */
export const TAMANO_RT = 512;
/** Opacidad del plano de la sombra (0–1). Calibrar a ojo en F3. */
export const OPACIDAD_CONTACTO = 0.7;
/** Oscuridad del pase de profundidad: alfa = (1 − profundidad) · OSCURIDAD. */
export const OSCURIDAD = 1;
/** Radio del desenfoque (unidades del ejemplo de three: `h = radio / 256`). Se pasa dos veces:
   con el radio y con 0,4 · radio. Calibrar en F3. */
export const RADIO_BLUR = 3.5;
/** Margen alrededor de la máquina en planta: fracción del lado mayor, con un mínimo en mm. */
export const MARGEN_FRACCION = 0.15;
export const MARGEN_MIN_MM = 150;
/** Hasta qué altura sobre el piso «ve» la sombra: fracción del alto de la máquina, con un mínimo
   en mm. Lo que está más arriba no oscurece el piso. */
export const ALCANCE_FRACCION = 0.5;
export const ALCANCE_MIN_MM = 100;
/** El plano va apenas bajo el `min.z` visible y sobre el suelo de la sombra direccional
   (`scene-setup.ts::updateGround` lo pone en `min.z − 0,5`). */
export const HOLGURA_PLANO_MM = 0.25;
/** Entre dos recálculos pasan al menos estos ms (10 Hz durante un arrastre o una animación). */
export const INTERVALO_MIN_MS = 100;

/** Dónde va la cámara de la sombra y qué cubre: centro en planta, altura del plano, lado del
   cuadrado (la máquina + margen) y alcance hacia arriba. */
export interface EncuadreSombra {
  cx: number;
  cy: number;
  z: number;
  lado: number;
  alcance: number;
}

/** Encuadre a partir del bbox de lo visible; null si no hay nada. Cuadrado (no el rectángulo
   del bbox) para que el desenfoque sea igual en X que en Y. */
export function encuadreSombra(caja: THREE.Box3): EncuadreSombra | null {
  if (caja.isEmpty()) return null;
  const sx = caja.max.x - caja.min.x;
  const sy = caja.max.y - caja.min.y;
  const sz = caja.max.z - caja.min.z;
  const mayor = Math.max(sx, sy);
  return {
    cx: (caja.min.x + caja.max.x) / 2,
    cy: (caja.min.y + caja.max.y) / 2,
    z: caja.min.z - HOLGURA_PLANO_MM,
    lado: mayor + 2 * Math.max(mayor * MARGEN_FRACCION, MARGEN_MIN_MM),
    alcance: Math.max(sz * ALCANCE_FRACCION, ALCANCE_MIN_MM) + HOLGURA_PLANO_MM,
  };
}

/** Coloca la cámara ortográfica (en el plano, mirando hacia +Z) y el plano de la sombra. Con
   `rotation.x = π` la derecha de la imagen es +X y su arriba es −Y: por eso la geometría del
   plano lleva la V invertida (`crearPlano`). */
export function aplicarEncuadre(camara: THREE.OrthographicCamera, plano: THREE.Object3D, e: EncuadreSombra): void {
  const h = e.lado / 2;
  camara.left = -h;
  camara.right = h;
  camara.top = h;
  camara.bottom = -h;
  camara.near = 0;
  camara.far = e.alcance;
  camara.position.set(e.cx, e.cy, e.z);
  camara.rotation.set(Math.PI, 0, 0);
  camara.updateProjectionMatrix();
  camara.updateMatrixWorld();
  plano.position.set(e.cx, e.cy, e.z);
  plano.scale.set(e.lado, e.lado, 1);
  plano.updateMatrixWorld();
}

/** Plano unidad en XY (normal +Z: desde abajo no se ve) con la V invertida, para que la textura
   que ve la cámara desde abajo caiga en su sitio. */
export function crearPlano(material: THREE.Material): THREE.Mesh {
  const geo = new THREE.PlaneGeometry(1, 1);
  const uv = geo.getAttribute("uv") as THREE.BufferAttribute;
  for (let i = 0; i < uv.count; i++) uv.setY(i, 1 - uv.getY(i));
  const plano = new THREE.Mesh(geo, material);
  plano.raycast = () => undefined; // no entra en el picking
  plano.castShadow = false;
  plano.receiveShadow = false;
  return plano;
}

/** Bandera `sucia` (D3): ¿toca recalcular en este frame? `continuo` = un arrastre o una animación
   en curso (las mallas se mueven sin avisar). Nunca dos recálculos a menos de `intervaloMs`; lo
   pedido en ese hueco queda pendiente y se hace en el primer frame que se pueda. Al terminar lo
   continuo se hace una pasada final. Nace sucia. */
export interface Programador {
  marcar: () => void;
  toca: (ahora: number, continuo: boolean) => boolean;
}

export function crearProgramador(intervaloMs = INTERVALO_MIN_MS): Programador {
  let sucia = true;
  let continuoAntes = false;
  let ultimo = -Infinity;
  return {
    marcar: () => { sucia = true; },
    toca: (ahora, continuo) => {
      if (continuoAntes && !continuo) sucia = true; // fin del arrastre: la pose final
      continuoAntes = continuo;
      if (!sucia && !continuo) return false; // reposo: costo cero
      if (ahora - ultimo < intervaloMs) return false; // sigue pendiente
      sucia = false;
      ultimo = ahora;
      return true;
    },
  };
}

export interface SombraContacto {
  /** Algo cambió (mallas, pose, física, visibilidad, sección): recalcular cuando toque. */
  marcarSucia: () => void;
  /** Planos de sección vigentes: la sombra es la de lo que se ve. Marca sucia. */
  fijarPlanos: (planos: THREE.Plane[]) => void;
  /** Tarea por frame, antes de componer. */
  actualizar: (ahora: number, continuo: boolean) => void;
  /** Cuántas veces se recalculó (E2E: en reposo no sube). */
  recalculos: () => number;
  dispose: () => void;
}

/** Lo que usa del renderer (un stub en los tests). */
export type RendererSombra = Pick<THREE.WebGLRenderer,
  "getRenderTarget" | "setRenderTarget" | "clear" | "render" | "getClearColor" | "getClearAlpha" | "setClearColor" | "shadowMap">;

export function crearSombraContacto(
  renderer: RendererSombra, scene: THREE.Scene, group: THREE.Object3D, ground: THREE.Object3D,
): SombraContacto {
  const rt = new THREE.WebGLRenderTarget(TAMANO_RT, TAMANO_RT);
  rt.texture.generateMipmaps = false;
  const rtBlur = new THREE.WebGLRenderTarget(TAMANO_RT, TAMANO_RT, { depthBuffer: false });
  rtBlur.texture.generateMipmaps = false;

  const material = new THREE.MeshBasicMaterial({
    map: rt.texture, color: 0x000000, transparent: true, opacity: OPACIDAD_CONTACTO, depthWrite: false,
  });
  const plano = crearPlano(material);
  plano.visible = false; // hasta el primer cálculo con algo visible
  scene.add(plano);

  const camara = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  // Profundidad → negro con alfa = (1 − z) · oscuridad. A diferencia del ejemplo de three, con
  // test de profundidad: bajo una pata gana lo más CERCANO al piso, no lo último dibujado.
  const profundidad = new THREE.MeshDepthMaterial();
  profundidad.side = THREE.DoubleSide; // superficies abiertas y chapas también apoyan
  profundidad.userData.oscuridad = { value: OSCURIDAD };
  profundidad.onBeforeCompile = (shader) => {
    shader.uniforms.oscuridad = profundidad.userData.oscuridad;
    shader.fragmentShader = "uniform float oscuridad;\n" + shader.fragmentShader.replace(
      "gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );",
      "gl_FragColor = vec4( vec3( 0.0 ), ( 1.0 - fragCoordZ ) * oscuridad );",
    );
  };

  const blurH = new THREE.ShaderMaterial(HorizontalBlurShader);
  const blurV = new THREE.ShaderMaterial(VerticalBlurShader);
  blurH.depthTest = blurV.depthTest = false;
  const quad = new FullScreenQuad(blurH);

  const desenfocar = (radio: number) => {
    quad.material = blurH;
    blurH.uniforms.tDiffuse.value = rt.texture;
    blurH.uniforms.h.value = radio / 256;
    renderer.setRenderTarget(rtBlur);
    quad.render(renderer as THREE.WebGLRenderer);
    quad.material = blurV;
    blurV.uniforms.tDiffuse.value = rtBlur.texture;
    blurV.uniforms.v.value = radio / 256;
    renderer.setRenderTarget(rt);
    quad.render(renderer as THREE.WebGLRenderer);
  };

  const prog = crearProgramador();
  const caja = new THREE.Box3();
  const colorPrevio = new THREE.Color();
  const ocultos: THREE.Object3D[] = [];
  let listo = false;
  let n = 0;

  const recalcular = () => {
    n++;
    const e = encuadreSombra(caja.setFromObject(group));
    listo = e !== null;
    if (!e) return;
    aplicarEncuadre(camara, plano, e);

    // sólo las piezas: fuera grid, ejes, suelo, gizmo, overlays, productos y el propio plano
    // (las luces quedan: apagarlas cambiaría el estado de luces de todos los materiales)
    ocultos.length = 0;
    for (const o of scene.children) {
      if (o === group || (o as THREE.Light).isLight || !o.visible) continue;
      o.visible = false;
      ocultos.push(o);
    }
    const previo = renderer.getRenderTarget();
    renderer.getClearColor(colorPrevio);
    const alfaPrevio = renderer.getClearAlpha();
    const fondo = scene.background;
    const { autoUpdate, needsUpdate } = renderer.shadowMap;
    renderer.shadowMap.autoUpdate = false; // el mapa de la luz direccional no se rehace aquí
    renderer.shadowMap.needsUpdate = false;
    scene.background = null;
    scene.overrideMaterial = profundidad;
    renderer.setClearColor(0x000000, 0);
    try {
      renderer.setRenderTarget(rt);
      renderer.clear();
      renderer.render(scene, camara);
      scene.overrideMaterial = null;
      for (const o of ocultos) o.visible = true;
      ocultos.length = 0;
      desenfocar(RADIO_BLUR);
      desenfocar(RADIO_BLUR * 0.4);
    } finally {
      scene.overrideMaterial = null;
      for (const o of ocultos) o.visible = true;
      scene.background = fondo;
      renderer.shadowMap.autoUpdate = autoUpdate;
      renderer.shadowMap.needsUpdate = needsUpdate;
      renderer.setClearColor(colorPrevio, alfaPrevio);
      renderer.setRenderTarget(previo);
    }
  };

  return {
    marcarSucia: prog.marcar,
    fijarPlanos: (planos) => {
      profundidad.clippingPlanes = planos.length ? planos : null;
      prog.marcar();
    },
    actualizar: (ahora, continuo) => {
      if (prog.toca(ahora, continuo)) recalcular();
      plano.visible = listo && ground.visible; // D5: sin suelo, sin sombra
    },
    recalculos: () => n,
    dispose: () => {
      scene.remove(plano);
      plano.geometry.dispose();
      material.dispose();
      profundidad.dispose();
      blurH.dispose();
      blurV.dispose();
      rt.dispose();
      rtBlur.dispose();
      // `quad` no se libera: su geometría es la compartida de three (la usan los passes del composer)
    },
  };
}
