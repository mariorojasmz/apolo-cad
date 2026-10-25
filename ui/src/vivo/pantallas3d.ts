import * as THREE from "three";
import type { Pantalla3D, VivoPantalla } from "../extensiones/tipos";
import { capturarToques } from "./mandos3d";
import { caraFrontal, matrizDeCara, pantallasDeLaSesion, rectanguloPantalla, uvAPx } from "./pantallas";
import type { DispositivoVivo } from "./protocolo";

/* Las pantallas 3D de las extensiones en el visor (plan plc-en-el-lazo, D13 b): por cada
   dispositivo de la sesión con pieza y una pantalla para su `tipo`, un plano con un
   `CanvasTexture` sobre la cara frontal de la pieza (`pantallas.ts`), a la resolución del
   dispositivo. La extensión pinta el canvas ≈ 10 veces por segundo; un toque se toma con la MISMA
   captura que los mandos 3D (`capturarToques`: no selecciona ni gira la cámara) y llega a su
   `tocar` en píxeles del canvas. El plano vive en `grupo` (como la cinta de la marcha), sigue a su
   pieza en cada cuadro y no se puede elegir (`raycast` no-op; el toque se prueba aparte). */

export interface Pantallas3D {
  tick: (nowMs: number) => void;
  quitar: () => void;
  /** Cuántas pantallas se instalaron (para el muestrario y los tests). */
  cuantas: number;
}

export interface OpcionesPantallas3D {
  contenedor: HTMLElement;
  canvas: HTMLCanvasElement;
  camara: () => THREE.Camera;
  meshes: Map<string, THREE.Mesh>;
  /** Donde cuelgan los planos (el `group` del visor). */
  grupo: THREE.Object3D;
  dispositivos: readonly DispositivoVivo[];
  pantallas: readonly Pantalla3D[];
  /** Lo que ve la pantalla de `d` al pintar o al tocarla (lo arma quien instala: sesión o muestrario). */
  vivo: (d: DispositivoVivo, ancho: number, alto: number) => VivoPantalla;
  /** Cada cuánto se repinta (ms). */
  cadaMs?: number;
}

interface Plano {
  d: DispositivoVivo;
  pantalla: Pantalla3D;
  pieza: THREE.Mesh;
  plano: THREE.Mesh;
  local: THREE.Matrix4;
  ctx: CanvasRenderingContext2D;
  textura: THREE.CanvasTexture;
  px: [number, number];
  /** La pantalla reventó al pintar: se avisa una vez y deja de pintarse. */
  rota: boolean;
}

const _ndc = new THREE.Vector2();
const _ray = new THREE.Raycaster();
const _inv = new THREE.Matrix4();
const noRaycast = () => {};

function crearPlano(d: DispositivoVivo, pantalla: Pantalla3D, pieza: THREE.Mesh): Plano | null {
  const pos = pieza.geometry.getAttribute("position");
  if (!pos) return null;
  pieza.updateWorldMatrix(true, false);
  const cara = caraFrontal(pos.array, pieza.geometry.index?.array ?? null, pieza.matrixWorld.elements);
  if (!cara || cara.ancho <= 0 || cara.alto <= 0) return null;
  const rect = rectanguloPantalla(cara.ancho, cara.alto, d.pantalla_px);
  const lienzo = document.createElement("canvas");
  [lienzo.width, lienzo.height] = rect.px;
  const ctx = lienzo.getContext("2d");
  if (!ctx) return null;
  const textura = new THREE.CanvasTexture(lienzo);
  textura.colorSpace = THREE.SRGBColorSpace;
  textura.anisotropy = 4;
  const plano = new THREE.Mesh(new THREE.PlaneGeometry(rect.ancho, rect.alto),
    new THREE.MeshBasicMaterial({ map: textura, toneMapped: false }));
  plano.matrixAutoUpdate = false;
  plano.raycast = noRaycast;
  plano.userData.pantalla = pantalla.id;
  return { d, pantalla, pieza, plano, local: new THREE.Matrix4().fromArray(matrizDeCara(cara)), ctx, textura,
    px: rect.px, rota: false };
}

export function instalarPantallas3D(o: OpcionesPantallas3D): Pantallas3D {
  const cada = o.cadaMs ?? 100;
  const planos: Plano[] = [];
  for (const { dispositivo, pantalla } of pantallasDeLaSesion(o.dispositivos, o.pantallas, (id) => o.meshes.has(id))) {
    const p = crearPlano(dispositivo, pantalla, o.meshes.get(dispositivo.pieza!)!);
    if (!p) continue;
    o.grupo.add(p.plano);
    planos.push(p);
  }
  const seguir = (p: Plano) => { // el plano, sobre su pieza (que puede moverse o girar con la puerta)
    p.pieza.updateWorldMatrix(true, false);
    o.grupo.updateWorldMatrix(true, false);
    p.plano.matrix.copy(_inv.copy(o.grupo.matrixWorld).invert()).multiply(p.pieza.matrixWorld).multiply(p.local);
    p.plano.matrixWorldNeedsUpdate = true;
    p.plano.updateWorldMatrix(false, false);
    p.plano.visible = p.pieza.visible;
  };
  const pintar = (p: Plano) => {
    if (p.rota) return;
    const [w, h] = p.px;
    try {
      p.ctx.save();
      p.pantalla.dibujar(p.ctx, o.vivo(p.d, w, h));
    } catch (e) {
      p.rota = true;
      console.error(`La pantalla «${p.pantalla.id}» de ${p.d.designacion} falló al pintar y se dejó de pintar:`, e);
    } finally {
      p.ctx.restore();
    }
    p.textura.needsUpdate = true;
  };
  for (const p of planos) { seguir(p); pintar(p); }

  // toques: el plano cuenta si el rayo lo toca antes que cualquier pieza visible
  const tocables = planos.filter((p) => p.pantalla.tocar);
  const alApretar = (ev: PointerEvent): boolean => {
    const r = o.canvas.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    _ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    _ray.setFromCamera(_ndc, o.camara());
    let mejor: { p: Plano; hit: THREE.Intersection } | null = null;
    for (const p of tocables) {
      if (!p.plano.visible) continue;
      seguir(p);
      const hits: THREE.Intersection[] = [];
      THREE.Mesh.prototype.raycast.call(p.plano, _ray, hits);
      const hit = hits[0];
      if (hit && hit.uv && (!mejor || hit.distance < mejor.hit.distance)) mejor = { p, hit };
    }
    if (!mejor) return false;
    const pieza = _ray.intersectObjects([...o.meshes.values()].filter((m) => m.visible), false)[0];
    if (pieza && pieza.distance < mejor.hit.distance - 1e-3) return false; // algo lo tapa
    const { p, hit } = mejor;
    const { x, y } = uvAPx(hit.uv!, p.px);
    try {
      p.pantalla.tocar!(x, y, o.vivo(p.d, p.px[0], p.px[1]));
    } catch (e) {
      console.error(`La pantalla «${p.pantalla.id}» de ${p.d.designacion} falló al tocarla:`, e);
    }
    pintar(p); // el toque se ve sin esperar al próximo repintado
    return true;
  };
  const soltarCaptura = tocables.length ? capturarToques(o.contenedor, alApretar) : () => {};

  let pintadoEn = -Infinity;
  return {
    cuantas: planos.length,
    tick: (nowMs) => {
      if (!planos.length) return;
      for (const p of planos) seguir(p);
      if (nowMs - pintadoEn < cada) return;
      pintadoEn = nowMs;
      for (const p of planos) pintar(p);
    },
    quitar: () => {
      soltarCaptura();
      for (const p of planos) {
        o.grupo.remove(p.plano);
        p.plano.geometry.dispose();
        (p.plano.material as THREE.Material).dispose();
        p.textura.dispose();
      }
      planos.length = 0;
    },
  };
}
