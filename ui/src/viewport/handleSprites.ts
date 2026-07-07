import * as THREE from "three";

/* Texturas de canvas + fábrica de SPRITES para los tiradores del overlay (look TinkerCad:
   cuadritos con borde + flechas de rotación, tamaño de pantalla constante). Aísla el <canvas>
   del resto. Los sprites miran a la cámara solos; el tamaño constante lo fija Viewport por
   frame. El color/hover se hace tintando `material.color` (las texturas son la FORMA). */

function squareTexture(fill: string, border: string): THREE.CanvasTexture {
  const s = 64, b = 8;
  const cv = document.createElement("canvas");
  cv.width = cv.height = s;
  const c = cv.getContext("2d")!;
  c.fillStyle = border;
  c.fillRect(0, 0, s, s);
  c.fillStyle = fill;
  c.fillRect(b, b, s - 2 * b, s - 2 * b);
  return toTex(cv);
}

function toTex(cv: HTMLCanvasElement): THREE.CanvasTexture {
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.needsUpdate = true;
  return tex;
}

let _light: THREE.CanvasTexture | null = null;
let _dark: THREE.CanvasTexture | null = null;
/** Cuadrito CLARO (relleno claro + borde oscuro) — esquinas / altura. */
export const squareLightTex = () => (_light ??= squareTexture("#f0f0f0", "#20232a"));
/** Cuadrito OSCURO (relleno oscuro + borde CLARO) — costados (visible sobre fondo oscuro). */
export const squareDarkTex = () => (_dark ??= squareTexture("#2b2e35", "#d2d6dd"));

/** Sprite de tirador: la textura es la FORMA, el color se tinta (base + hover). */
export function makeHandleSprite(map: THREE.CanvasTexture, baseColor: number): THREE.Sprite {
  const mat = new THREE.SpriteMaterial({ map, color: baseColor, depthTest: false, transparent: true });
  const sp = new THREE.Sprite(mat);
  sp.userData.baseColor = baseColor;
  sp.renderOrder = 106;
  return sp;
}
