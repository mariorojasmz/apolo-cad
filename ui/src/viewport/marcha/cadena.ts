import * as THREE from "three";
import { valorEn, type CadenaSerie, type SerieMarcha } from "./serie";

/* Cadenas que avanzan eslabón por eslabón (plan visor-realista, D6). La cadena del CAD es UN
   sólido por lazo y no puede avanzar: en marcha se oculta y se dibujan sus rodillos, pernos y
   placas como instancias (`InstancedMesh`): las cadenas iguales (misma norma y mismo aspecto)
   comparten un juego de cuatro, así mil eslabones son cuatro llamadas de dibujo.

   El rodillo físico m ocupa la posición m + n(t) del lazo, con n = signo·(q(t) − q(0))/360·z (los
   rodillos del servidor son los de la geometría, en orden antihorario sobre +Z, el sentido en que
   avanza el lazo cuando giran sus piñones). Entre dos rodillos sentados en el mismo piñón el
   rodillo gira alrededor de su eje (no corta la cuerda); en los tramos, va en recta. Después de un
   paso entero la cadena vuelve a coincidir con la del CAD. Las placas interiores unen los rodillos
   (2k, 2k+1) y las exteriores (2k+1, 2k+2): como el índice es el del rodillo FÍSICO, las placas
   viajan con él. */

export interface Punto2 {
  x: number;
  y: number;
}

/** ¿El índice k del lazo es un rodillo sentado en ese piñón ([primero, cuántos])? */
function sentado(k: number, rango: [number, number]): boolean {
  return k >= rango[0] && k < rango[0] + rango[1];
}

/** Centro (marco del lazo) del rodillo que está en la posición `p` (real) del lazo. */
export function posicionEnLazo(c: CadenaSerie, p: number, out: Punto2): Punto2 {
  const n = c.puntos.length / 2;
  const base = Math.floor(p);
  const f = p - base;
  const k = ((base % n) + n) % n;
  const k2 = (k + 1) % n;
  const ax = c.puntos[2 * k], ay = c.puntos[2 * k + 1];
  const bx = c.puntos[2 * k2], by = c.puntos[2 * k2 + 1];
  let centro: [number, number] | null = null;
  if (sentado(k, c.asentados_a) && sentado(k2, c.asentados_a)) centro = [0, 0];
  else if (sentado(k, c.asentados_b) && sentado(k2, c.asentados_b)) centro = c.centro_b;
  if (centro && f > 0) {
    const a0 = Math.atan2(ay - centro[1], ax - centro[0]);
    let da = Math.atan2(by - centro[1], bx - centro[0]) - a0;
    da = Math.atan2(Math.sin(da), Math.cos(da)); // el arco corto: un diente
    const r = Math.hypot(ax - centro[0], ay - centro[1]);
    out.x = centro[0] + r * Math.cos(a0 + f * da);
    out.y = centro[1] + r * Math.sin(a0 + f * da);
    return out;
  }
  out.x = ax + (bx - ax) * f;
  out.y = ay + (by - ay) * f;
  return out;
}

/** Avance del lazo en pasos en el tramo (i, f) de la serie. */
export function avanceCadena(c: CadenaSerie, serie: SerieMarcha, i: number, f: number): number {
  const q = serie.juntas[c.junta]?.q ?? [];
  if (!q.length) return 0;
  return (c.signo * (valorEn(q, i, f) - q[0]) * c.z) / 360;
}

/** Placa de eslabón: estadio de largo `paso` entre centros (en +X desde el origen), alto `alto`,
 *  extruida `espesor` en +Z. */
function geometriaPlaca(paso: number, alto: number, espesor: number): THREE.BufferGeometry {
  const r = alto / 2;
  const s = new THREE.Shape();
  s.absarc(0, 0, r, Math.PI / 2, (3 * Math.PI) / 2, false);
  s.absarc(paso, 0, r, -Math.PI / 2, Math.PI / 2, false);
  s.closePath();
  return new THREE.ExtrudeGeometry(s, { depth: espesor, bevelEnabled: false, curveSegments: 8 });
}

/** Cilindro de eje Z centrado en el origen. */
function geometriaCilindro(d: number, largo: number): THREE.BufferGeometry {
  return new THREE.CylinderGeometry(d / 2, d / 2, largo, 14).rotateX(Math.PI / 2);
}

/** Lo que define la forma de los eslabones (dos cadenas con la misma clave comparten mallas). */
function claveForma(c: CadenaSerie): string {
  return JSON.stringify([c.paso, c.rodillo_d, c.perno_d, c.alto_placa, c.espesor_placa, c.capas]);
}

/** Lo que define cómo se VE un material: cada pieza trae su propio material (`buildSolidMaterial`),
 *  pero dos cadenas con el mismo acabado se ven igual y comparten el juego de instancias. */
export function claveAspecto(m: THREE.Material): string {
  const s = m as THREE.MeshStandardMaterial;
  return [s.type, s.color?.getHexString(), s.metalness, s.roughness, s.wireframe, s.transparent,
    s.opacity, s.bumpMap?.uuid, s.clippingPlanes?.length ?? 0].join("|");
}

export interface CadenasEnMarcha {
  objetos: THREE.Object3D[];
  /** Piezas del CAD que se reemplazan (se ocultan mientras dura la marcha). */
  piezas: string[];
  posar: (i: number, f: number) => void;
  dispose: () => void;
}

const _m = new THREE.Matrix4();
const _t = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _p = new THREE.Vector3();
const _s = new THREE.Vector3();
const _z = new THREE.Vector3(0, 0, 1);

/** Instancias por rodillo, perno, placa interior y exterior de UNA cadena. */
function porCadena(c: CadenaSerie): [number, number, number, number] {
  const n = c.puntos.length / 2;
  return [n * c.capas.rodillos.length, n, (n / 2) * c.capas.interiores.length, (n / 2) * c.capas.exteriores.length];
}

/** Las cadenas animables de la serie como instancias. `material(pieza)` da el acabado de cada
 *  una (el de su malla del CAD). */
export function crearCadenas(serie: SerieMarcha, material: (pieza: string) => THREE.Material): CadenasEnMarcha {
  const cadenas = (serie.cadenas ?? []).filter((c) => c.puntos.length >= 8 && (c.puntos.length / 2) % 2 === 0);
  const juegos = new Map<string, { mat: THREE.Material; lista: CadenaSerie[] }>();
  for (const c of cadenas) {
    const mat = material(c.pieza);
    const clave = `${claveAspecto(mat)}|${claveForma(c)}`;
    const j = juegos.get(clave) ?? { mat, lista: [] };
    j.lista.push(c);
    juegos.set(clave, j);
  }
  const objetos: THREE.InstancedMesh[] = [];
  const posadores: ((i: number, f: number) => void)[] = [];
  for (const { mat, lista } of juegos.values()) {
    const c0 = lista[0];
    const totales = [0, 0, 0, 0];
    for (const c of lista) porCadena(c).forEach((v, k) => (totales[k] += v));
    const geos = [
      geometriaCilindro(c0.rodillo_d, c0.capas.rodillos[0][1] - c0.capas.rodillos[0][0]),
      geometriaCilindro(c0.perno_d, c0.capas.perno[1] - c0.capas.perno[0]),
      geometriaPlaca(c0.paso, c0.alto_placa, c0.espesor_placa),
      geometriaPlaca(c0.paso, c0.alto_placa, c0.espesor_placa),
    ];
    const mallas = geos.map((g, k) => {
      const im = new THREE.InstancedMesh(g, mat, totales[k]);
      im.castShadow = im.receiveShadow = true;
      im.raycast = () => {}; // no se elige: la pieza es la cadena del CAD
      im.userData.marcha = true;
      objetos.push(im);
      return im;
    });
    const [rodillos, pernos, interiores, exteriores] = mallas;
    posadores.push((i, f) => {
      const k = [0, 0, 0, 0]; // siguiente instancia libre de cada malla
      for (const c of lista) posarCadena(c, serie, i, f, mallas, k);
      for (const im of [rodillos, pernos, interiores, exteriores]) {
        im.instanceMatrix.needsUpdate = true;
        im.boundingBox = null; // se recalculan solos (encuadre, sombra, recorte)
        im.boundingSphere = null;
      }
    });
  }
  return {
    objetos,
    piezas: cadenas.map((c) => c.pieza),
    posar: (i, f) => {
      for (const p of posadores) p(i, f);
    },
    dispose: () => {
      for (const o of objetos) {
        o.geometry.dispose();
        o.dispose();
      }
    },
  };
}

const _pts: Punto2[] = [];

function posarCadena(c: CadenaSerie, serie: SerieMarcha, i: number, f: number,
  [rodillos, pernos, interiores, exteriores]: THREE.InstancedMesh[], k: number[]): void {
  const n = c.puntos.length / 2;
  while (_pts.length < n) _pts.push({ x: 0, y: 0 });
  const marco = _marco.set(...(c.marco as Parameters<THREE.Matrix4["set"]>));
  const enMarco = (x: number, y: number, z: number, ang: number, escalaX: number) => {
    _p.set(x, y, z);
    _q.setFromAxisAngle(_z, ang);
    _s.set(escalaX, 1, 1);
    return _m.multiplyMatrices(marco, _t.compose(_p, _q, _s));
  };
  const zc = (z: [number, number]) => (z[0] + z[1]) / 2;
  const av = avanceCadena(c, serie, i, f);
  for (let m = 0; m < n; m++) posicionEnLazo(c, m + av, _pts[m]);
  for (const capa of c.capas.rodillos) {
    for (let m = 0; m < n; m++) rodillos.setMatrixAt(k[0]++, enMarco(_pts[m].x, _pts[m].y, zc(capa), 0, 1));
  }
  for (let m = 0; m < n; m++) pernos.setMatrixAt(k[1]++, enMarco(_pts[m].x, _pts[m].y, zc(c.capas.perno), 0, 1));
  for (let m = 0; m < n; m++) {
    const a = _pts[m], b = _pts[(m + 1) % n];
    const ang = Math.atan2(b.y - a.y, b.x - a.x);
    const esc = Math.hypot(b.x - a.x, b.y - a.y) / c.paso;
    const interior = m % 2 === 0;
    for (const capa of interior ? c.capas.interiores : c.capas.exteriores) {
      if (interior) interiores.setMatrixAt(k[2]++, enMarco(a.x, a.y, capa[0], ang, esc));
      else exteriores.setMatrixAt(k[3]++, enMarco(a.x, a.y, capa[0], ang, esc));
    }
  }
}

const _marco = new THREE.Matrix4();
