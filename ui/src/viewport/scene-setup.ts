import * as THREE from "three";

/* Configuración del render PBR: renderer (tone mapping + sombras), luces y
   suelo receptor de sombras. Mantiene la cámara/controles/gizmo en Viewport.tsx
   (acoplados al picking) — aquí solo lo que define el "aspecto". */

export function createRenderer(): THREE.WebGLRenderer {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setClearColor(0x1b1e24);
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

export function createGround(scene: THREE.Scene): THREE.Mesh {
  // Plano XY (Z es arriba) que SOLO muestra la sombra (ShadowMaterial), sin
  // tapar el grid ni el fondo. Fuera del grupo => no entra en el raycast de
  // selección ni recibe clippingPlanes (no se corta con la sección).
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.ShadowMaterial({ opacity: 0.25 }),
  );
  ground.receiveShadow = true;
  ground.castShadow = false;
  ground.raycast = () => undefined;
  ground.renderOrder = -1;
  scene.add(ground);
  return ground;
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
