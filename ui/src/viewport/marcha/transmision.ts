import * as THREE from "three";
import { avanceCadena, crearCadenas } from "./cadena";
import { crearFajas, giroRodillo } from "./faja";
import type { RodilloFaja, SerieMarcha } from "./serie";

/* La faja y las cadenas de la marcha (plan visor-realista, D6), sobre las mallas reales: oculta la
   cadena y la banda del CAD (sólidos rígidos), pone en su lugar las instancias de eslabones y la
   cinta con su forma real, y hace girar lo que la banda o la cadena arrastran sin que la física lo
   mueva (tambor de cola, rodillos de retorno, el piñón del motor sin junta). Lo llama el
   reproductor en cada pose, DESPUÉS de mover los cuerpos de junta: lo que gira y además viaja en
   un cuerpo (un tensor que se desliza) compone su giro sobre esa pose. Una pieza oculta por el
   usuario sigue oculta (no se dibuja su reemplazo). */

export interface TransmisionEnMarcha {
  posar: (i: number, f: number) => void;
  restaurar: () => void;
}

const _g = new THREE.Matrix4();
const _inv = new THREE.Matrix4();
const _v = new THREE.Vector3();

/** Una malla que gira arrastrada: su eje (`radio_mm` 1 → el «recorrido» es el ángulo en rad). */
interface Giro {
  mesh: THREE.Mesh;
  base: THREE.Matrix4;
  baseInv: THREE.Matrix4;
  eje: RodilloFaja;
  recorrido: (i: number, f: number) => number;
}

/** `movidas`: las mallas que el reproductor ya posa con T(t)·base (cuerpos de junta). */
export function crearTransmision(
  serie: SerieMarcha,
  meshes: Map<string, THREE.Mesh>,
  grupo: THREE.Object3D,
  movidas: Set<THREE.Mesh>,
): TransmisionEnMarcha {
  const visible = (id: string) => meshes.get(id)?.visible === true;
  const material = (id: string) => {
    const m = meshes.get(id)?.material;
    return (Array.isArray(m) ? m[0] : m) ?? null;
  };
  const filtrada: SerieMarcha = {
    ...serie,
    cadenas: (serie.cadenas ?? []).filter((c) => visible(c.pieza)),
    fajas: (serie.fajas ?? []).filter((f) => visible(f.pieza)),
  };
  const cadenas = crearCadenas(filtrada, (p) => material(p) ?? new THREE.MeshStandardMaterial({ color: "#3b3e43" }));
  const fajas = crearFajas(filtrada, material);
  const ocultas = [...cadenas.piezas, ...fajas.piezas].map((id) => meshes.get(id)!);
  for (const m of ocultas) m.visible = false;
  const objetos = [...cadenas.objetos, ...fajas.objetos];
  for (const o of objetos) grupo.add(o);

  const giros: Giro[] = [];
  const sumar = (pieza: string, eje: RodilloFaja, recorrido: Giro["recorrido"]) => {
    const mesh = meshes.get(pieza);
    const base = mesh?.userData.baseMatrix as THREE.Matrix4 | undefined;
    if (!mesh || !base || giros.some((g) => g.mesh === mesh)) return;
    mesh.matrixAutoUpdate = false;
    giros.push({ mesh, base, baseInv: base.clone().invert(), eje, recorrido });
  };
  let recorridos = new Map<string, number>();
  for (const f of filtrada.fajas ?? []) {
    for (const r of f.rodillos) sumar(r.pieza, r, () => recorridos.get(f.pieza) ?? 0);
  }
  for (const c of filtrada.cadenas ?? []) {
    if (!cadenas.piezas.includes(c.pieza)) continue;
    const marco = new THREE.Matrix4().set(...(c.marco as Parameters<THREE.Matrix4["set"]>));
    const z = new THREE.Vector3().setFromMatrixColumn(marco, 2).normalize();
    for (const p of c.pinones_libres ?? []) {
      const centro = (p.lado === "a" ? _v.set(0, 0, 0) : _v.set(c.centro_b[0], c.centro_b[1], 0)).applyMatrix4(marco);
      const eje: RodilloFaja = { pieza: p.pieza, centro: centro.toArray(), eje: z.toArray(), radio_mm: 1 };
      sumar(p.pieza, eje, (i, f) => (2 * Math.PI * avanceCadena(c, serie, i, f)) / p.z);
    }
  }

  return {
    posar: (i, f) => {
      cadenas.posar(i, f);
      recorridos = fajas.posar(i, f);
      for (const { mesh, base, baseInv, eje, recorrido } of giros) {
        giroRodillo(eje, recorrido(i, f), _g);
        if (movidas.has(mesh)) {
          // la pose del cuerpo ya está en la malla (T·base): T·G·base = (T·base)·base⁻¹·G·base
          _inv.copy(mesh.matrix).multiply(baseInv);
          mesh.matrix.multiplyMatrices(_inv, _g).multiply(base);
        } else {
          mesh.matrix.multiplyMatrices(_g, base);
        }
        mesh.matrixWorldNeedsUpdate = true;
      }
    },
    restaurar: () => {
      for (const m of ocultas) m.visible = true;
      for (const o of objetos) o.removeFromParent();
      cadenas.dispose();
      fajas.dispose();
      for (const { mesh } of giros) {
        mesh.matrixAutoUpdate = true;
        const p0 = mesh.userData.p0 as THREE.Vector3 | undefined;
        const q0 = mesh.userData.q0 as THREE.Quaternion | undefined;
        if (p0) mesh.position.copy(p0);
        if (q0) mesh.quaternion.copy(q0);
        mesh.updateMatrix();
        mesh.matrixWorldNeedsUpdate = true;
      }
    },
  };
}
