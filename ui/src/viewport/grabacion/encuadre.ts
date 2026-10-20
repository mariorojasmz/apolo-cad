import * as THREE from "three";
import { direccion } from "./planGuion";

/* Encuadre del video (plan video-realista, F2 y F3). La cámara del visor viene con el aspecto de
   la ventana y lejos (el «encuadrar» del visor deja aire de sobra): para el video se acerca lo
   justo para que la máquina entre en el cuadro de 16:9.

   - `encuadreGiro` (F2, el giro): UNA distancia para todo el giro, por búsqueda binaria sobre
     las 8 esquinas de la caja.
   - `distanciasPorAngulo` (F3, el guion): la distancia MÍNIMA en cada ángulo, sobre puntos de la
     máquina (los vértices de sus mallas, submuestreados, con los extremos de cada una), con un
     máximo en una ventana de ±`VENTANA_GRADOS` y un promedio de ±`SUAVIZADO_GRADOS` encima: la
     cámara se acerca y se aleja lento y sin tirones, y en ningún ángulo queda más cerca que lo
     que ese ángulo permite (cada término del promedio es un máximo que lo contiene). Una máquina
     larga llena el cuadro de costado y se aleja sola al verla de punta.

   La prueba usa un clon de la cámara con `near` = 1: el `near` del visor se ajusta por cuadro
   (`recorte.ts`) y puede valer cientos de mm; heredado, empujaba la cámara lejos. */

/** Fracción del cuadro que puede ocupar la máquina en el giro de F2 (deja un margen). */
export const MARGEN = 0.86;
/** La del video del guion (F3): más justa, la distancia ya sigue a cada ángulo. */
export const MARGEN_VIDEO = 0.92;
/** Ángulos del giro que se prueban en F2 (cada 10° en una vuelta). */
const ANGULOS = 36;
/** F3: cada cuánto se mide la distancia, la ventana del máximo y la del promedio (grados). */
export const PASO_GRADOS = 5;
export const VENTANA_GRADOS = 20;
export const SUAVIZADO_GRADOS = 15;
/** Tope de puntos de la máquina para encuadrar (unos ms por ángulo). */
export const PUNTOS_MAX = 6000;

const _v = new THREE.Vector3();
const _p = new THREE.Vector3();

function esquinas(caja: THREE.Box3): THREE.Vector3[] {
  const { min, max } = caja;
  const out: THREE.Vector3[] = [];
  for (const x of [min.x, max.x]) for (const y of [min.y, max.y]) for (const z of [min.z, max.z]) {
    out.push(new THREE.Vector3(x, y, z));
  }
  return out;
}

/** Un clon de la cámara para las pruebas, con `near` chico (ver arriba). */
function camaraDePrueba(camara: THREE.PerspectiveCamera): THREE.PerspectiveCamera {
  const prueba = camara.clone();
  prueba.near = 1;
  prueba.updateProjectionMatrix();
  return prueba;
}

/** ¿Todos los `puntos` caen dentro de ±`margen` del cuadro, con la cámara en `posicion`
   mirando a `objetivo`? */
function entran(prueba: THREE.PerspectiveCamera, posicion: THREE.Vector3, objetivo: THREE.Vector3,
  puntos: readonly THREE.Vector3[], margen: number): boolean {
  prueba.position.copy(posicion);
  prueba.lookAt(objetivo);
  prueba.updateMatrixWorld(true);
  for (const p of puntos) {
    _p.copy(p).applyMatrix4(prueba.matrixWorldInverse);
    if (_p.z >= -prueba.near) return false; // detrás de la cámara
    _p.applyMatrix4(prueba.projectionMatrix);
    if (Math.abs(_p.x) > margen || Math.abs(_p.y) > margen) return false;
  }
  return true;
}

/** La menor distancia desde `objetivo` en la dirección `dir` con la que entran los puntos. */
function distanciaMinima(prueba: THREE.PerspectiveCamera, objetivo: THREE.Vector3, dir: THREE.Vector3,
  puntos: readonly THREE.Vector3[], diag: number, margen: number): number {
  const en = (d: number) => entran(prueba, _v.copy(dir).multiplyScalar(d).add(objetivo), objetivo, puntos, margen);
  let cerca = diag * 0.05;
  let lejos = diag * 20;
  if (!en(lejos)) return lejos;
  for (let i = 0; i < 32; i++) {
    const medio = (cerca + lejos) / 2;
    if (en(medio)) lejos = medio;
    else cerca = medio;
  }
  return lejos;
}

/** Posición de cámara que encuadra `caja` mirando a su centro desde la dirección `desde`→centro
   actual, para un giro de `grados` alrededor de Z. Devuelve también el nuevo objetivo. */
export function encuadreGiro(
  camara: THREE.PerspectiveCamera, objetivoActual: THREE.Vector3, caja: THREE.Box3, grados: number,
  margen = MARGEN,
): { posicion: THREE.Vector3; objetivo: THREE.Vector3 } | null {
  if (caja.isEmpty()) return null;
  const centro = caja.getCenter(new THREE.Vector3());
  const dir = camara.position.clone().sub(objetivoActual).normalize();
  if (!Number.isFinite(dir.x)) return null;
  const prueba = camaraDePrueba(camara);
  const puntos = esquinas(caja);
  const diag = caja.getSize(new THREE.Vector3()).length() || 1000;
  const eje = new THREE.Vector3(0, 0, 1);
  const d = new THREE.Vector3();
  const todas = (dist: number) => {
    for (let k = 0; k <= ANGULOS; k++) {
      const a = THREE.MathUtils.degToRad((grados * k) / ANGULOS);
      d.copy(dir).applyAxisAngle(eje, a);
      if (!entran(prueba, d.clone().multiplyScalar(dist).add(centro), centro, puntos, margen)) return false;
    }
    return true;
  };
  let cerca = diag * 0.05;
  let lejos = diag * 20;
  if (!todas(lejos)) return null;
  for (let i = 0; i < 40; i++) {
    const medio = (cerca + lejos) / 2;
    if (todas(medio)) lejos = medio;
    else cerca = medio;
  }
  return { posicion: centro.clone().add(dir.multiplyScalar(lejos)), objetivo: centro };
}

/** Puntos de la máquina en el mundo: los vértices de cada malla submuestreados hasta `tope`
   en total, más los seis extremos de cada una (así ninguna pieza chica se pierde). */
export function puntosDeMallas(mallas: Iterable<THREE.Mesh>, tope = PUNTOS_MAX): THREE.Vector3[] {
  const lista = [...mallas].filter((m) => m.geometry?.getAttribute("position"));
  const total = lista.reduce((n, m) => n + m.geometry.getAttribute("position").count, 0);
  const paso = Math.max(1, Math.ceil(total / Math.max(1, tope)));
  const out: THREE.Vector3[] = [];
  for (const m of lista) {
    m.updateWorldMatrix(true, false);
    const pos = m.geometry.getAttribute("position");
    const ext: THREE.Vector3[] = [];
    for (let i = 0; i < pos.count; i++) {
      const esPaso = i % paso === 0;
      const p = new THREE.Vector3().fromBufferAttribute(pos, i).applyMatrix4(m.matrixWorld);
      if (esPaso) out.push(p);
      if (ext.length === 0) {
        for (let k = 0; k < 6; k++) ext.push(p.clone());
        continue;
      }
      for (let eje = 0; eje < 3; eje++) {
        if (p.getComponent(eje) < ext[2 * eje].getComponent(eje)) ext[2 * eje].copy(p);
        if (p.getComponent(eje) > ext[2 * eje + 1].getComponent(eje)) ext[2 * eje + 1].copy(p);
      }
    }
    out.push(...ext);
  }
  return out;
}

const circular = (k: number, n: number) => ((k % n) + n) % n;

/** La distancia de la cámara al `objetivo` para cada azimut (grados, cualquier vuelta), con la
   `elevacion` fija: mínima por ángulo, máximo en ±VENTANA y promedio en ±SUAVIZADO (arriba). */
export function distanciasPorAngulo(
  camara: THREE.PerspectiveCamera, objetivo: THREE.Vector3, puntos: readonly THREE.Vector3[],
  elevacion: number, margen = MARGEN_VIDEO,
): (azimut: number) => number {
  const caja = new THREE.Box3().setFromPoints(puntos as THREE.Vector3[]);
  const diag = caja.isEmpty() ? 1000 : caja.getSize(new THREE.Vector3()).length() || 1000;
  if (puntos.length === 0) return () => diag * 1.5;
  const prueba = camaraDePrueba(camara);
  const n = Math.round(360 / PASO_GRADOS);
  const dir = new THREE.Vector3();
  const minima = Array.from({ length: n }, (_, k) => {
    dir.fromArray(direccion(k * PASO_GRADOS, elevacion));
    return distanciaMinima(prueba, objetivo, dir, puntos, diag, margen);
  });
  const radio = (grados: number) => Math.round(grados / PASO_GRADOS);
  const maximo = minima.map((_, k) => {
    let m = 0;
    for (let j = -radio(VENTANA_GRADOS); j <= radio(VENTANA_GRADOS); j++) m = Math.max(m, minima[circular(k + j, n)]);
    return m;
  });
  const suave = maximo.map((_, k) => {
    let s = 0;
    const r = radio(SUAVIZADO_GRADOS);
    for (let j = -r; j <= r; j++) s += maximo[circular(k + j, n)];
    return s / (2 * r + 1);
  });
  return (azimut) => {
    const x = azimut / PASO_GRADOS;
    const k = Math.floor(x);
    const f = x - k;
    return suave[circular(k, n)] * (1 - f) + suave[circular(k + 1, n)] * f;
  };
}

/** Qué fracción del ANCHO del cuadro ocupan los puntos con la cámara como está (0–1). */
export function anchoOcupado(camara: THREE.PerspectiveCamera, puntos: readonly THREE.Vector3[]): number {
  camara.updateMatrixWorld(true);
  let min = Infinity;
  let max = -Infinity;
  for (const p of puntos) {
    _p.copy(p).project(camara);
    min = Math.min(min, _p.x);
    max = Math.max(max, _p.x);
  }
  return puntos.length ? (Math.min(max, 1) - Math.max(min, -1)) / 2 : 0;
}
