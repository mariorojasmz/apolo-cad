import * as THREE from "three";
import type { FajaSerie, RodilloFaja, SerieMarcha } from "./serie";

/* La faja con su forma real (plan visor-realista, D6). El servidor manda la ruta de la línea media
   de la banda en el plano de la faja (abraza sus tambores y cuelga entre los apoyos del retorno,
   `library/ruta_faja.py`); aquí se arma la cinta (cara de afuera, de adentro y cantos) con UV en
   mm: u = recorrido a lo largo de la ruta, v = a lo ancho. En marcha la cinta NO se mueve: corre su
   textura, desplazada el recorrido s(t) de la banda (la integral de su velocidad en la serie). El
   empalme —la marca que se ve en una banda real— está en s = 0, donde cierra la textura. */

/** Ancho (mm) de la franja del empalme. */
export const EMPALME_MM = 40;

/** Recorrido acumulado (mm) por muestra: trapecios de la velocidad (m/s). */
export function recorridos(t: number[], v: number[]): number[] {
  const s = [0];
  for (let k = 1; k < Math.min(t.length, v.length); k++) {
    s.push(s[k - 1] + 0.5 * (v[k] + v[k - 1]) * (t[k] - t[k - 1]) * 1000);
  }
  return s;
}

/** Recorrido ANTIHORARIO de la ruta (mm) en el tramo (i, f): signo · s(t). */
export function recorridoEn(f: FajaSerie, s: number[], i: number, fr: number): number {
  if (!s.length) return 0;
  const a = s[Math.min(i, s.length - 1)];
  const b = s[Math.min(i + 1, s.length - 1)];
  return f.signo * (a + (b - a) * fr);
}

function aMundo(f: FajaSerie, u: number, w: number, v: number, out: THREE.Vector3): THREE.Vector3 {
  const { origen: o, u: U, w: W, v: V } = f.marco;
  return out.set(
    o[0] + u * U[0] + w * W[0] + v * V[0],
    o[1] + u * U[1] + w * W[1] + v * V[1],
    o[2] + u * U[2] + w * W[2] + v * V[2],
  );
}

/** La cinta de la banda en mundo, con UV en mm y normales por cara. La ruta es antihoraria en
 *  (u, w): la normal hacia afuera es la derecha del recorrido. Se repite el primer punto al final
 *  (con u = largo) para que la UV no salte en el cierre. */
export function geometriaFaja(f: FajaSerie): THREE.BufferGeometry {
  const n = f.ruta.length / 2;
  const P = (k: number) => [f.ruta[2 * (k % n)], f.ruta[2 * (k % n) + 1]];
  // normal afuera en cada punto: promedio de la de los dos tramos que lo tocan
  const normales: [number, number][] = [];
  for (let k = 0; k < n; k++) {
    const [a0, a1] = P(k + n - 1), [b0, b1] = P(k), [c0, c1] = P(k + 1);
    const l1 = Math.hypot(b0 - a0, b1 - a1) || 1, l2 = Math.hypot(c0 - b0, c1 - b1) || 1;
    let nu = (b1 - a1) / l1 + (c1 - b1) / l2, nw = -(b0 - a0) / l1 - (c0 - b0) / l2;
    const l = Math.hypot(nu, nw) || 1;
    nu /= l; nw /= l;
    normales.push([nu, nw]);
  }
  const s: number[] = [0];
  for (let k = 1; k <= n; k++) {
    const [a0, a1] = P(k - 1), [b0, b1] = P(k);
    s.push(s[k - 1] + Math.hypot(b0 - a0, b1 - a1));
  }
  const pos: number[] = [], nor: number[] = [], uv: number[] = [], idx: number[] = [];
  const h = f.espesor / 2, v0 = f.v_centro - f.ancho / 2, v1 = f.v_centro + f.ancho / 2;
  const p = new THREE.Vector3(), q = new THREE.Vector3(), o = new THREE.Vector3();
  aMundo(f, 0, 0, 0, o);
  const dirMundo = (du: number, dw: number, dv: number) => aMundo(f, du, dw, dv, q).sub(o);
  // 4 caras: afuera (+h), adentro (−h), canto v0 y canto v1
  const caras: [number, number, number, number][] = [[h, h, v0, v1], [-h, -h, v1, v0], [-h, h, v0, v0], [h, -h, v1, v1]];
  caras.forEach(([ha, hb, va, vb], cara) => {
    const base = pos.length / 3;
    for (let k = 0; k <= n; k++) {
      const [pu, pw] = P(k);
      const [nu, nw] = normales[k % n];
      for (const [hh, vv] of [[ha, va], [hb, vb]] as const) {
        aMundo(f, pu + nu * hh, pw + nw * hh, vv, p);
        pos.push(p.x, p.y, p.z);
        const nn = cara === 0 ? dirMundo(nu, nw, 0) : cara === 1 ? dirMundo(-nu, -nw, 0)
          : dirMundo(0, 0, cara === 2 ? -1 : 1);
        nor.push(nn.x, nn.y, nn.z);
        uv.push(s[k], cara < 2 ? vv - v0 : hh + h);
      }
      if (k < n) {
        const a = base + 2 * k;
        idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
      }
    }
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeBoundingBox();
  g.computeBoundingSphere();
  return g;
}

/** Mapa de color del empalme: blanco (no cambia el color de la banda) con una franja más oscura
 *  en u ∈ [0, EMPALME_MM) de cada vuelta. 64 × 1, se repite una vez por largo de la banda. */
export function texturaEmpalme(largo: number): THREE.DataTexture {
  const ancho = 256;
  const datos = new Uint8Array(ancho * 4);
  const franja = Math.max(1, Math.round((EMPALME_MM / Math.max(largo, EMPALME_MM)) * ancho));
  for (let x = 0; x < ancho; x++) {
    const v = x < franja ? 150 : 255;
    datos.set([v, v, v, 255], x * 4);
  }
  const tex = new THREE.DataTexture(datos, ancho, 1, THREE.RGBAFormat);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.magFilter = THREE.NearestFilter;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.repeat.set(1 / largo, 1);
  tex.needsUpdate = true;
  return tex;
}

/** Corre una textura que repite cada 1/repeat.x mm: el dibujo que estaba en u queda en u + s. */
export function correrTextura(tex: THREE.Texture, s: number): void {
  const x = -s * tex.repeat.x;
  tex.offset.x = x - Math.floor(x);
}

const _r = new THREE.Matrix4();
const _c = new THREE.Matrix4();
const _ci = new THREE.Matrix4();
const _eje = new THREE.Vector3();

/** Matriz del giro de un rodillo libre en el mundo: alrededor de su eje por su centro, ángulo =
 *  recorrido / radio (rad). */
export function giroRodillo(r: RodilloFaja, s: number, out: THREE.Matrix4): THREE.Matrix4 {
  const [x, y, z] = r.centro;
  _eje.set(r.eje[0], r.eje[1], r.eje[2]).normalize();
  _r.makeRotationAxis(_eje, s / r.radio_mm);
  _c.makeTranslation(x, y, z);
  _ci.makeTranslation(-x, -y, -z);
  return out.multiplyMatrices(_c, _r).multiply(_ci);
}

export interface FajaEnMarcha {
  objetos: THREE.Object3D[];
  piezas: string[];
  /** Recorrido antihorario (mm) de cada faja (por pieza) en el tramo: lo usan sus rodillos libres. */
  posar: (i: number, f: number) => Map<string, number>;
  dispose: () => void;
}

/** Las cintas de la serie. `material(pieza)` es el material de la banda del CAD: se clona (con
 *  su relieve propio para correrlo) y se le suma el empalme. */
export function crearFajas(serie: SerieMarcha, material: (pieza: string) => THREE.Material | null): FajaEnMarcha {
  const objetos: THREE.Mesh[] = [];
  const corredores: { f: FajaSerie; s: number[]; texturas: THREE.Texture[] }[] = [];
  for (const f of serie.fajas ?? []) {
    if (f.ruta.length < 6 || !(f.largo_mm > 0)) continue;
    const banda = serie.bandas.find((b) => b.pieza === f.pieza);
    const base = material(f.pieza);
    const mat = (base instanceof THREE.MeshStandardMaterial ? base.clone() : new THREE.MeshStandardMaterial({ color: "#2f5b3b", roughness: 0.72 }));
    const texturas: THREE.Texture[] = [];
    if (mat.bumpMap) {
      mat.bumpMap = mat.bumpMap.clone(); // comparte la imagen; offset propio
      mat.bumpMap.needsUpdate = true;
      texturas.push(mat.bumpMap);
    }
    mat.map = texturaEmpalme(f.largo_mm);
    texturas.push(mat.map);
    mat.side = THREE.FrontSide;
    const malla = new THREE.Mesh(geometriaFaja(f), mat);
    malla.castShadow = malla.receiveShadow = true;
    malla.raycast = () => {};
    malla.userData.marcha = true;
    objetos.push(malla);
    corredores.push({ f, s: banda ? recorridos(serie.t, banda.v_m_s) : [], texturas });
  }
  const recorrido = new Map<string, number>();
  return {
    objetos,
    piezas: corredores.map((c) => c.f.pieza),
    posar: (i, fr) => {
      for (const { f, s, texturas } of corredores) {
        const sc = recorridoEn(f, s, i, fr);
        recorrido.set(f.pieza, sc);
        for (const t of texturas) correrTextura(t, sc);
      }
      return recorrido;
    },
    dispose: () => {
      for (const m of objetos) {
        m.geometry.dispose();
        const mat = m.material as THREE.MeshStandardMaterial;
        mat.map?.dispose();
        mat.bumpMap?.dispose(); // el clon: three cuenta los usos de la imagen compartida
        mat.dispose();
      }
    },
  };
}
