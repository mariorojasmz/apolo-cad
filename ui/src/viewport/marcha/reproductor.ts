import * as THREE from "three";
import { ACABADOS } from "../acabados";
import { poseEn, poseProducto, tramo, type SerieMarcha } from "./serie";

/* Reproductor de la marcha (plan visor-realista, D4): mueve las MALLAS REALES de cada cuerpo de
   junta y unas cajas de producto (overlay efímero, como las del drop-test) según la serie del
   servidor, interpolando en cada fotograma del bucle de render (`pipeline.antesDeComponer`).

   Matemática: la serie trae por cuerpo T(t) = P(t)·P(0)⁻¹ (la transformación desde la pose de
   diseño), así que cada pieza del cuerpo va a  mesh.matrix = T(t) · baseMatrix  (su malla de
   diseño en el mundo). Las cajas traen su pose absoluta (centro) y nacen en su muestra `desde`.
   Nada de esto toca el documento: al quitar la marcha las mallas vuelven a su pose base. */

/** Lo que el reproductor lee de la línea de tiempo en cada fotograma (`estado.ts`). */
export interface Mando {
  reproduciendo: boolean;
  velocidad: number;
  salto: number | null;
}

/** A quién avisa el reproductor: la línea de tiempo y la sombra de contacto. */
export interface AvisosReproductor {
  saltoHecho: () => void;
  /** Tiempo para la barra (como mucho cada `PUBLICAR_MS`) y si llegó al final. */
  publicar: (t: number, alFinal: boolean) => void;
  /** Se movieron mallas: la sombra de contacto queda sucia (piso-con-sombra, D3). */
  alPosar: () => void;
}

export interface Reproductor {
  tick: (nowMs: number) => void;
  /** Tiempo actual de la reproducción (s). */
  tiempo: () => number;
  /** Devuelve las mallas a su pose base y retira las cajas. */
  restaurar: () => void;
}

/** Cada cuánto se publica el tiempo a la barra (ms): 10 Hz, sin re-render por fotograma. */
export const PUBLICAR_MS = 100;

const _m = new THREE.Matrix4();

interface PiezaMovida {
  mesh: THREE.Mesh;
  base: THREE.Matrix4;
  poses: number[];
}

/** Una caja por producto con el acabado «cartón» de la tabla D5; ocultas hasta que nacen. */
function cajasProducto(serie: SerieMarcha, grupo: THREE.Group): Map<string, THREE.Mesh> {
  const carton = ACABADOS.carton;
  const cajas = new Map<string, THREE.Mesh>();
  for (const p of serie.productos) {
    const [w, d, h] = p.dims_mm;
    const material = new THREE.MeshStandardMaterial({
      color: carton?.color ?? "#b48a5a",
      metalness: carton?.metalness ?? 0,
      roughness: carton?.roughness ?? 0.9,
    });
    const caja = new THREE.Mesh(new THREE.BoxGeometry(w, d, h), material);
    caja.castShadow = true;
    caja.receiveShadow = true;
    caja.matrixAutoUpdate = false;
    caja.visible = false;
    caja.userData.marcha = true;
    cajas.set(p.name, caja);
    grupo.add(caja);
  }
  return cajas;
}

export function crearReproductor(
  serie: SerieMarcha,
  meshes: Map<string, THREE.Mesh>,
  escena: THREE.Object3D,
  leer: () => Mando,
  avisos: AvisosReproductor,
  tInicial = 0,
): Reproductor {
  const piezas: PiezaMovida[] = [];
  for (const c of Object.values(serie.cuerpos)) {
    for (const id of c.piezas) {
      const mesh = meshes.get(id);
      const base = mesh?.userData.baseMatrix as THREE.Matrix4 | undefined;
      if (!mesh || !base) continue; // pieza oculta o sin malla: se salta
      mesh.matrixAutoUpdate = false;
      piezas.push({ mesh, base, poses: c.poses });
    }
  }
  const grupo = new THREE.Group();
  grupo.name = "marcha-productos";
  const cajas = cajasProducto(serie, grupo);
  escena.add(grupo);

  const dur = serie.duracion_s;
  const animable = serie.t.length >= 2 && dur > 0;
  let t = Math.min(Math.max(0, tInicial), dur);
  let ultimo = 0;
  let publicadoEn = -Infinity;

  const posar = (x: number) => {
    const { i, f } = tramo(serie.t, x);
    for (const p of piezas) {
      poseEn(p.poses, i, f, _m);
      p.mesh.matrix.copy(_m).multiply(p.base);
      p.mesh.matrixWorldNeedsUpdate = true;
    }
    for (const prod of serie.productos) {
      const caja = cajas.get(prod.name)!;
      caja.visible = poseProducto(prod, i, f, caja.matrix);
      caja.matrixWorldNeedsUpdate = true;
    }
    avisos.alPosar();
  };
  posar(t);

  return {
    tiempo: () => t,
    tick: (nowMs) => {
      const { reproduciendo, velocidad, salto } = leer();
      let movio = false;
      if (salto !== null) {
        t = Math.min(Math.max(0, salto), dur);
        avisos.saltoHecho();
        movio = true;
      }
      if (reproduciendo && animable) {
        if (ultimo) t += ((nowMs - ultimo) / 1000) * Math.max(0.05, velocidad);
        movio = true;
      }
      ultimo = reproduciendo ? nowMs : 0;
      if (!movio) return;
      const alFinal = reproduciendo && t >= dur;
      if (alFinal) t = dur;
      posar(t);
      if (alFinal || nowMs - publicadoEn >= PUBLICAR_MS || salto !== null) {
        publicadoEn = nowMs;
        avisos.publicar(t, alFinal);
      }
    },
    restaurar: () => {
      for (const { mesh } of piezas) {
        mesh.matrixAutoUpdate = true;
        const p0 = mesh.userData.p0 as THREE.Vector3 | undefined;
        const q0 = mesh.userData.q0 as THREE.Quaternion | undefined;
        if (p0) mesh.position.copy(p0);
        if (q0) mesh.quaternion.copy(q0);
        mesh.updateMatrix();
        mesh.matrixWorldNeedsUpdate = true;
      }
      for (const caja of cajas.values()) {
        caja.geometry.dispose();
        (caja.material as THREE.Material).dispose();
      }
      grupo.clear();
      escena.remove(grupo);
      avisos.alPosar();
    },
  };
}
