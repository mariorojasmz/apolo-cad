import * as THREE from "three";

/* ESTUDIO procedural para la luz de ambiente de la calidad «alta» (video-realista D1): una sala
   gris en degradé con cuatro softboxes emisivos (principal, relleno, contorno y cenital) que
   `PMREMGenerator` convierte en el IBL. A diferencia de `RoomEnvironment`, da recortes de luz
   nítidos que el metal refleja (lo que lo hace leer como metal) y no depende de un HDRI bajado
   (CSP, licencia, tamaño). Z arriba, como el visor; la principal viene del mismo lado que la luz
   direccional (`scene-setup.ts::LIGHT_OFFSET`), así la sombra y el reflejo cuentan lo mismo.
   Unidades arbitrarias: `fromScene` mira con near 0,1 y far 100. */

export interface Softbox {
  /** Hacia dónde está, visto desde la máquina (no hace falta normalizar). */
  dir: [number, number, number];
  ancho: number;
  alto: number;
  /** Radiancia (blanco × intensidad): > 1 es lo que hace brillar el reflejo. */
  intensidad: number;
}

export const SOFTBOXES: Record<string, Softbox> = {
  principal: { dir: [0.55, -0.45, 0.7], ancho: 7, alto: 5, intensidad: 9 },
  relleno: { dir: [-0.75, -0.55, 0.35], ancho: 8, alto: 5, intensidad: 2.2 },
  contorno: { dir: [-0.1, 0.9, 0.45], ancho: 12, alto: 2.2, intensidad: 7 },
  cenital: { dir: [0, 0, 1], ancho: 10, alto: 10, intensidad: 2.5 },
};
/** Distancia de los softboxes al centro y radio de la sala. */
export const DISTANCIA = 14;
export const RADIO_SALA = 30;
/** Desenfoque del PMREM (sigma, radianes): bajo = los recortes siguen nítidos. */
export const SIGMA = 0.02;

/** Gris de la sala según la altura (−1 piso … 1 cenit): horizonte algo más claro. */
export function grisSala(z: number): number {
  return z >= 0 ? 0.22 - 0.12 * z : 0.16 + 0.06 * z;
}

export function crearEstudio(): THREE.Scene {
  const escena = new THREE.Scene();
  const geo = new THREE.SphereGeometry(RADIO_SALA, 48, 24);
  geo.rotateX(Math.PI / 2); // polos en ±Z
  const pos = geo.getAttribute("position");
  const col = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    col[i * 3] = col[i * 3 + 1] = col[i * 3 + 2] = grisSala(pos.getZ(i) / RADIO_SALA);
  }
  geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
  escena.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide })));

  for (const [nombre, sb] of Object.entries(SOFTBOXES)) {
    const mat = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide });
    mat.color.setScalar(sb.intensidad);
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(sb.ancho, sb.alto), mat);
    panel.name = nombre;
    const d = new THREE.Vector3(...sb.dir).normalize();
    panel.position.copy(d).multiplyScalar(DISTANCIA);
    panel.up.set(0, 0, 1);
    if (Math.abs(d.z) > 0.99) panel.up.set(0, 1, 0); // el cenital: lookAt necesita otro «arriba»
    panel.lookAt(0, 0, 0);
    escena.add(panel);
  }
  return escena;
}

/** Libera geometrías y materiales de la escena del estudio (después del PMREM ya no sirve). */
export function liberarEscena(escena: THREE.Object3D): void {
  escena.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (mesh.geometry) mesh.geometry.dispose();
    const mat = mesh.material as THREE.Material | THREE.Material[] | undefined;
    if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
    else if (mat) mat.dispose();
  });
}
