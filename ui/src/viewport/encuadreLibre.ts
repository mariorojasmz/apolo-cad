import * as THREE from "three";
import { AREA_COMPLETA, type AreaNdc } from "./areaLibre";
import type { PoseCamara } from "./camara";

/* El encuadre que se VE (plan visor-para-evaluar D13–D15), para todo pedido de encuadre:
   - centra y mide la caja en el área libre del visor (sin el panel lateral, `areaLibre.ts`);
   - con `frente`, mira la cara grande de esa pieza de frente (la normal de la puerta de un
     tablero), no desde el ángulo que tenía la cámara;
   - con `despejar`, si otra pieza tapa la caja prueba vistas cercanas y, si todas están tapadas,
     devuelve qué atenuar.
   Puro sobre three.js (sin DOM): lo usan `interaccion/ergonomia.ts` y los tests. */

/** Distancia de siempre (`camara.destinoEncuadre`): 1,4 × la diagonal de la caja. */
const FACTOR_DISTANCIA = 1.4;

/** La pose que encuadra `box` mirando desde `dir` (del objetivo a la cámara) dentro de `area`.
   Con el área completa da la MISMA pose que `destinoEncuadre` (la distancia de siempre); con un
   área menor se aleja lo que el área achica y corre el objetivo para que la caja quede en su
   centro. null con la caja vacía. */
export function poseEnArea(
  box: THREE.Box3, dir: THREE.Vector3, camara: { fov: number; aspect: number; up: THREE.Vector3 },
  area: AreaNdc = AREA_COMPLETA,
): PoseCamara | null {
  if (box.isEmpty()) return null;
  const centro = box.getCenter(new THREE.Vector3());
  const diag = box.getSize(new THREE.Vector3()).length() || 1200;
  const d = dir.clone().normalize();
  if (!(d.lengthSq() > 0)) return null;
  const t = Math.tan(THREE.MathUtils.degToRad(camara.fov) / 2);
  const a = camara.aspect > 0 ? camara.aspect : 1;
  const hx = Math.max((area.x1 - area.x0) / 2, 0.05), hy = Math.max((area.y1 - area.y0) / 2, 0.05);
  // lo que hace falta alejarse para que la esfera de la caja quepa en el área, relativo al área completa
  const necesita = (h: number, v: number) => Math.max(1 / (t * v), 1 / (t * a * h));
  const D = diag * FACTOR_DISTANCIA * (necesita(hx, hy) / necesita(1, 1));
  const cx = (area.x0 + area.x1) / 2, cy = (area.y0 + area.y1) / 2;
  const adelante = d.clone().negate();
  const derecha = new THREE.Vector3().crossVectors(adelante, camara.up);
  if (derecha.lengthSq() < 1e-9) derecha.set(1, 0, 0); // mirando sobre el eje «arriba»
  derecha.normalize();
  const arriba = new THREE.Vector3().crossVectors(derecha, adelante).normalize();
  const objetivo = centro.clone()
    .addScaledVector(derecha, -cx * D * t * a)
    .addScaledVector(arriba, -cy * D * t);
  return { posicion: objetivo.clone().addScaledVector(d, D), objetivo };
}

/** La normal de la cara dominante de una malla, en mundo: el autovector mayor de Σ área·n·nᵀ de
   sus triángulos (una placa da la normal de sus dos caras grandes, sin signo). null sin área. */
export function normalDominante(malla: THREE.Mesh, matriz?: THREE.Matrix4): THREE.Vector3 | null {
  const g = malla.geometry as THREE.BufferGeometry | undefined;
  const pos = g?.getAttribute("position");
  if (!g || !pos) return null;
  const idx = g.getIndex();
  const n = idx ? idx.count : pos.count;
  const m = [0, 0, 0, 0, 0, 0, 0, 0, 0];
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), cr = new THREE.Vector3();
  for (let i = 0; i + 2 < n; i += 3) {
    const [i0, i1, i2] = idx ? [idx.getX(i), idx.getX(i + 1), idx.getX(i + 2)] : [i, i + 1, i + 2];
    a.fromBufferAttribute(pos, i0); b.fromBufferAttribute(pos, i1); c.fromBufferAttribute(pos, i2);
    cr.crossVectors(b.sub(a), c.sub(a)); // |cr| = 2·área; cr·crᵀ/|cr| = 2·área·n·nᵀ
    const l = cr.length();
    if (!(l > 0)) continue;
    const v = [cr.x, cr.y, cr.z];
    for (let r = 0; r < 3; r++) for (let k = 0; k < 3; k++) m[r * 3 + k] += (v[r] * v[k]) / l;
  }
  if (!(m[0] + m[4] + m[8] > 0)) return null;
  let v = new THREE.Vector3(1, 0.7, 0.4); // iteración de potencia: converge al autovector mayor
  for (let it = 0; it < 40; it++) {
    const w = new THREE.Vector3(m[0] * v.x + m[1] * v.y + m[2] * v.z, m[3] * v.x + m[4] * v.y + m[5] * v.z,
      m[6] * v.x + m[7] * v.y + m[8] * v.z);
    if (!(w.lengthSq() > 0)) return null;
    v = w.normalize();
  }
  if (matriz) return v.transformDirection(matriz).normalize();
  malla.updateWorldMatrix(true, false);
  return v.transformDirection(malla.matrixWorld).normalize();
}

/** La matriz de mundo de la pieza en su pose de DISEÑO (`userData.baseMatrix`: sin la junta
   aplicada), o la de ahora si no la tiene. Una puerta ya abierta se mira por su cara cerrada. */
export function matrizDeDiseno(malla: THREE.Mesh): THREE.Matrix4 {
  const base = malla.userData.baseMatrix as THREE.Matrix4 | undefined;
  malla.updateWorldMatrix(true, false);
  if (!base) return malla.matrixWorld.clone();
  return malla.parent ? malla.parent.matrixWorld.clone().multiply(base) : base.clone();
}

/** La caja de la pieza en su pose de diseño (la puerta cerrada). */
export function cajaDeDiseno(malla: THREE.Mesh): THREE.Box3 {
  const g = malla.geometry as THREE.BufferGeometry;
  if (!g.boundingBox) g.computeBoundingBox();
  return g.boundingBox!.clone().applyMatrix4(matrizDeDiseno(malla));
}

/** La dirección desde la que se mira el frente de `malla`: su normal dominante EN SU POSE DE
   DISEÑO (la puerta cerrada, aunque ya esté abierta), hacia AFUERA de `caja` (la del gabinete);
   si la pieza está en el centro, hacia donde ya estaba la cámara. */
export function direccionFrente(malla: THREE.Mesh, caja: THREE.Box3, camara: THREE.Vector3): THREE.Vector3 | null {
  const n = normalDominante(malla, matrizDeDiseno(malla));
  if (!n) return null;
  const cMalla = cajaDeDiseno(malla).getCenter(new THREE.Vector3());
  const cCaja = caja.getCenter(new THREE.Vector3());
  const afuera = cMalla.clone().sub(cCaja);
  const ref = afuera.lengthSq() > 1e-6 ? afuera : camara.clone().sub(cCaja);
  return n.dot(ref) < 0 ? n.negate() : n;
}

/** La caja de un frente que ABRE hacia la cámara (la puerta de un tablero gira hasta su ancho):
   la caja crece por delante tanto como la pieza mide y, a los lados, lo que la hoja pasa de la
   bisagra al abrir más de 90° (un tercio de su ancho). Pura: no muta `caja`. */
export function cajaConApertura(caja: THREE.Box3, frente: THREE.Box3, dir: THREE.Vector3): THREE.Box3 {
  const lado = frente.getSize(new THREE.Vector3());
  const crece = Math.max(lado.x, lado.y, lado.z);
  return caja.clone().union(frente.clone().translate(dir.clone().normalize().multiplyScalar(crece)))
    .expandByScalar(crece / 3);
}

/** Las vistas a probar si la principal está tapada, en orden de preferencia: la principal, ±30°
   de rumbo, 25° más alta y las dos combinadas (D15). Sólo giran alrededor de «arriba». */
export function vistasCandidatas(dir: THREE.Vector3, arriba: THREE.Vector3): THREE.Vector3[] {
  const d = dir.clone().normalize();
  const eje = arriba.clone().normalize();
  const rumbo = (g: number) => d.clone().applyAxisAngle(eje, THREE.MathUtils.degToRad(g));
  const subir = (v: THREE.Vector3, g: number) => {
    const lado = new THREE.Vector3().crossVectors(eje, v);
    if (lado.lengthSq() < 1e-9) return v.clone();
    return v.clone().applyAxisAngle(lado.normalize(), -THREE.MathUtils.degToRad(g));
  };
  return [d, rumbo(30), rumbo(-30), subir(d, 25), subir(rumbo(30), 25), subir(rumbo(-30), 25)];
}

/** Puntos de la caja que tienen que verse: su centro y las ocho esquinas llevadas al 70 %. */
export function puntosDeMuestra(caja: THREE.Box3): THREE.Vector3[] {
  const c = caja.getCenter(new THREE.Vector3());
  const out = [c];
  for (const x of [caja.min.x, caja.max.x]) for (const y of [caja.min.y, caja.max.y]) for (const z of [caja.min.z, caja.max.z]) {
    out.push(new THREE.Vector3(x, y, z).lerp(c, 0.3));
  }
  return out;
}

/** Las piezas que tapan `caja` vista desde `desde`: lo primero que cruza el rayo a cada punto de
   muestra, si está FUERA de la caja (lo de adentro —el interior de un tablero— no tapa) y no es
   una de `propias`. Devuelve los ids (únicos) y cuántos puntos quedaron tapados. */
export function queTapa(
  desde: THREE.Vector3, caja: THREE.Box3, mallas: readonly THREE.Object3D[], propias: ReadonlySet<string>,
  raycaster = new THREE.Raycaster(),
): { ids: string[]; tapados: number } {
  const ids = new Set<string>();
  let tapados = 0;
  const holgada = caja.clone().expandByScalar(1);
  for (const p of puntosDeMuestra(caja)) {
    const hacia = p.clone().sub(desde);
    const dist = hacia.length();
    if (!(dist > 0)) continue;
    raycaster.set(desde, hacia.divideScalar(dist));
    raycaster.far = dist;
    const golpe = raycaster.intersectObjects(mallas as THREE.Object3D[], false)
      .find((h) => !propias.has(String(h.object.userData.featureId)) && !holgada.containsPoint(h.point));
    if (golpe) {
      tapados += 1;
      ids.add(String(golpe.object.userData.featureId));
    }
  }
  return { ids: [...ids], tapados };
}

export interface VistaElegida {
  pose: PoseCamara;
  /** Lo que sigue tapando en la vista elegida (se atenúa): vacío si se encontró una libre. */
  atenuar: string[];
}

/** La primera vista libre de `vistasCandidatas` encuadrando `caja` (la que se mide) y mirando
   `ver` (lo que tiene que verse: el gabinete, sin el contexto); si ninguna está libre, la
   principal con lo que la tapa para atenuar (D15: el frente pedido manda sobre un ángulo raro). */
export function elegirVista(
  caja: THREE.Box3, ver: THREE.Box3, dir: THREE.Vector3,
  camara: { fov: number; aspect: number; up: THREE.Vector3 },
  area: AreaNdc, mallas: readonly THREE.Object3D[], propias: ReadonlySet<string>,
): VistaElegida | null {
  const raycaster = new THREE.Raycaster();
  let primera: VistaElegida | null = null;
  for (const d of vistasCandidatas(dir, camara.up)) {
    const pose = poseEnArea(caja, d, camara, area);
    if (!pose) return null;
    const { ids } = queTapa(pose.posicion, ver, mallas, propias, raycaster);
    if (!ids.length) return { pose, atenuar: [] };
    if (!primera) primera = { pose, atenuar: ids };
  }
  return primera;
}
