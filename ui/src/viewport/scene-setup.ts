import * as THREE from "three";

/* Configuración del render PBR: renderer (tone mapping + sombras), luces y
   suelo receptor de sombras. Mantiene la cámara/controles/gizmo en Viewport.tsx
   (acoplados al picking) — aquí solo lo que define el "aspecto". */

export const BACKGROUND = 0x1b1e24; // color de fondo del viewport (fuente única)
export const BACKGROUND_CSS = "#" + BACKGROUND.toString(16).padStart(6, "0"); // mismo color para el <div>

export function createRenderer(): THREE.WebGLRenderer {
  // alpha:true → el canvas es TRANSPARENTE donde no hay geometría. El color de fondo lo pinta el
  // <div> contenedor por CSS (ver BACKGROUND_CSS): así el fondo NO pasa por el tone-mapping del
  // EffectComposer/OutputPass (que lo teñía de gris al aplicarle ACES al color de limpiado).
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setClearColor(BACKGROUND, 0); // alpha 0 = fondo transparente (deja ver el CSS del div)
  renderer.localClippingEnabled = true; // el plano de sección depende de esto
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  return renderer;
}

export interface LightRig {
  hemi: THREE.HemisphereLight;
  dir: THREE.DirectionalLight;
}

const LIGHT_OFFSET = new THREE.Vector3(1500, -1000, 2000);

export function createLights(scene: THREE.Scene): LightRig {
  // Con IBL (scene.environment) aportando el ambiente, la hemisférica baja mucho.
  const hemi = new THREE.HemisphereLight(0xffffff, 0x3a3f4a, 0.3);
  scene.add(hemi);

  const dir = new THREE.DirectionalLight(0xffffff, 2.0);
  dir.position.copy(LIGHT_OFFSET);
  dir.castShadow = true;
  dir.shadow.mapSize.set(2048, 2048);
  dir.shadow.bias = -0.0005;
  dir.shadow.normalBias = 1; // mitiga acné de sombra con material DoubleSide
  scene.add(dir);
  scene.add(dir.target);
  return { hemi, dir };
}

/** Opacidad de la sombra DIRECCIONAL en el suelo. Baja (antes 0,25) para que bajo las patas
   mande la sombra de contacto (`sombraContacto.ts`, plan piso-con-sombra D4); la direccional
   queda para la sombra propia. Calibrar a ojo en F3. */
export const OPACIDAD_SOMBRA_DIRECCIONAL = 0.15;

export function createGround(scene: THREE.Scene): THREE.Mesh {
  // Plano XY (Z es arriba) que SOLO muestra la sombra (ShadowMaterial), sin
  // tapar el grid ni el fondo. Fuera del grupo => no entra en el raycast de
  // selección ni recibe clippingPlanes (no se corta con la sección).
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.ShadowMaterial({ opacity: OPACIDAD_SOMBRA_DIRECCIONAL }),
  );
  ground.receiveShadow = true;
  ground.castShadow = false;
  ground.raycast = () => undefined;
  ground.renderOrder = -1;
  scene.add(ground);
  const estudio = crearPisoEstudio();
  scene.add(estudio);
  ground.userData.estudio = estudio; // lo coloca updateGround junto con el suelo
  return ground;
}

/** Piso de ESTUDIO (plan piso-con-sombra, calibración de F3): un disco apenas más claro que el
   fondo bajo la máquina, que se desvanece hacia el borde. Sobre el fondo casi negro la sombra de
   contacto (negra) no tenía contra qué verse; sobre este gris medio, la máquina se lee apoyada. */
export const PISO_ESTUDIO_COLOR = 0x4a515c;
/** Radio del disco como múltiplo de la mitad del lado mayor de la máquina en planta. */
export const PISO_ESTUDIO_RADIO = 1.6;

export function crearPisoEstudio(): THREE.Mesh {
  const material = new THREE.ShaderMaterial({
    uniforms: { color: { value: new THREE.Color(PISO_ESTUDIO_COLOR) } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    // opaco al centro y transparente en el borde (caída suave: no se ve el contorno del disco)
    fragmentShader: "uniform vec3 color; varying vec2 vUv; void main(){ float r = length(vUv - 0.5) * 2.0; float a = 1.0 - smoothstep(0.15, 1.0, r); gl_FragColor = vec4(color, a * 0.9); }",
    transparent: true,
    depthWrite: false,
  });
  const disco = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
  disco.raycast = () => undefined;
  disco.castShadow = false;
  disco.receiveShadow = false;
  disco.renderOrder = -2; // primero el piso, encima la sombra direccional y la de contacto
  return disco;
}

/* Reposiciona el suelo bajo el bbox del modelo (en coordenadas de mundo) y
   ajusta la luz direccional + su cámara de sombra para cubrirlo. Se llama tras
   reconstruir las mallas (y al posar cinemática). */
export function updateGround(ground: THREE.Mesh, dir: THREE.DirectionalLight, box: THREE.Box3): void {
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = (Math.max(size.x, size.y, size.z) || 1200) * 0.5;

  const planeSize = Math.max(size.x, size.y) * 3 + 400;
  ground.scale.set(planeSize, planeSize, 1);
  ground.position.set(center.x, center.y, box.min.z - 0.5);
  const estudio = ground.userData.estudio as THREE.Mesh | undefined;
  if (estudio) {
    const d = Math.max(size.x, size.y) * PISO_ESTUDIO_RADIO + 400;
    estudio.scale.set(d, d, 1);
    estudio.position.set(center.x, center.y, box.min.z - 1);
  }

  // luz a offset fijo del centro -> iluminación consistente sin importar dónde
  // esté el modelo; frustum de sombra ortográfico dimensionado al bbox.
  dir.position.copy(center).add(LIGHT_OFFSET);
  dir.target.position.copy(center);
  dir.target.updateMatrixWorld();

  const cam = dir.shadow.camera as THREE.OrthographicCamera;
  const r = radius * 1.6 + 200;
  cam.left = -r;
  cam.right = r;
  cam.top = r;
  cam.bottom = -r;
  cam.near = 1;
  cam.far = LIGHT_OFFSET.length() + radius * 4 + 2000;
  cam.updateProjectionMatrix();
}
