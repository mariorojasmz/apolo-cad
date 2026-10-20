import * as THREE from "three";
import { intensidadResalte } from "./planGuion";

/* El montaje del video en el visor (plan video-realista, D5): las piezas de la máquina terminada
   aparecen tanda por tanda, como en el video de VTK, y lo que entra se resalta con el color de
   acento y se desvanece (`linea_tiempo.resalte`). Sólo se tocan las piezas que la persona tenía a
   la vista: una oculta sigue oculta. El resaltado clona el material (no muta los compartidos,
   como el tinte de bloqueo) y `restaurar` deja cada malla con su material y su visibilidad. */

/** El acento del video (`media/composicion.py` · `Estilo.color_acento`). */
export const ACENTO = new THREE.Color(91 / 255, 140 / 255, 1);
/** Cuánto brilla lo que entra en el primer cuadro (el emisivo se suma al PBR). */
export const BRILLO_RESALTE = 0.3;

type Material = THREE.Material & { emissive?: THREE.Color; emissiveIntensity?: number };

export interface Montaje {
  /** Las piezas que se van a montar (las visibles de la lista que tienen malla). */
  readonly ids: readonly string[];
  /** Esconde todas: el video empieza sin nada montado. */
  vaciar: () => void;
  /** Las piezas que entran en el cuadro `n` (se resaltan desde ahí). */
  sumar: (ids: readonly string[], n: number) => void;
  /** La máquina terminada entera, sin resaltes. */
  completar: () => void;
  /** Aplica el resaltado del cuadro `n`; quita el que ya se apagó. */
  resaltar: (n: number, fps: number, resalteS: number) => void;
  /** Caja de lo que se va a montar (para encuadrar todo el video). */
  caja: () => THREE.Box3;
  /** Las mallas de lo que se va a montar (sus vértices encuadran el video). */
  mallas: () => THREE.Mesh[];
  /** Cada malla vuelve a su material y visibilidad de antes. */
  restaurar: () => void;
}

export function crearMontaje(meshes: Map<string, THREE.Mesh>, ids: readonly string[]): Montaje {
  const mallas = new Map<string, THREE.Mesh>();
  for (const id of ids) {
    const m = meshes.get(id);
    if (m && m.visible) mallas.set(id, m);
  }
  const resaltes = new Map<string, { n0: number; original: THREE.Material; copia: Material }>();
  const apagar = (id: string) => {
    const r = resaltes.get(id);
    const m = mallas.get(id);
    if (!r || !m) return;
    m.material = r.original;
    r.copia.dispose();
    resaltes.delete(id);
  };
  return {
    ids: [...mallas.keys()],
    vaciar: () => {
      for (const id of [...resaltes.keys()]) apagar(id);
      for (const m of mallas.values()) m.visible = false;
    },
    sumar: (nuevos, n) => {
      for (const id of nuevos) {
        const m = mallas.get(id);
        if (!m) continue;
        m.visible = true;
        if (resaltes.has(id) || Array.isArray(m.material) || !m.material) continue;
        const original = m.material as THREE.Material;
        const copia = original.clone() as Material;
        if (!copia.emissive) {
          copia.dispose();
          continue; // un material sin emisivo (líneas) no se resalta
        }
        m.material = copia;
        resaltes.set(id, { n0: n, original, copia });
      }
    },
    completar: () => {
      for (const id of [...resaltes.keys()]) apagar(id);
      for (const m of mallas.values()) m.visible = true;
    },
    resaltar: (n, fps, resalteS) => {
      for (const [id, r] of [...resaltes]) {
        const k = intensidadResalte(n, r.n0, fps, resalteS);
        if (k <= 0) {
          apagar(id);
          continue;
        }
        r.copia.emissive!.copy(ACENTO);
        r.copia.emissiveIntensity = BRILLO_RESALTE * k;
      }
    },
    caja: () => {
      const caja = new THREE.Box3();
      for (const m of mallas.values()) caja.expandByObject(m);
      return caja;
    },
    mallas: () => [...mallas.values()],
    restaurar: () => {
      for (const id of [...resaltes.keys()]) apagar(id);
      for (const m of mallas.values()) m.visible = true;
    },
  };
}
