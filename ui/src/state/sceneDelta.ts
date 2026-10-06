/**
 * Refresco de escena por DELTA (V6.2b), en funciones PURAS: el store pide el delta al
 * servidor y aplica lo que devuelven. `mergeSceneDelta` reconstruye la escena completa;
 * `cambiosDelDelta` dice qué piezas trajo nuevas, con geometría nueva o eliminadas (el visor
 * las marca, plan modo-visor D8). Salió de `store.ts` para hacer lugar bajo su trinquete (D12).
 */
import type { FeatureOut, SceneOut } from "../types";

/** Reconstruye una SceneOut COMPLETA a partir de un delta (V6.2b): las features `same`
 * heredan la geometría (mesh/bbox/volumen/mesh_key/matrix) de la escena anterior y solo
 * reciben los metadatos volátiles; las demás llegan completas. Definiciones = las previas
 * (las `same` las conservan) + las nuevas del delta, podadas a las realmente referenciadas. */
export function mergeSceneDelta(prev: SceneOut, delta: SceneOut): SceneOut {
  const prevById = new Map(prev.features.map((f) => [f.id, f]));
  const features: FeatureOut[] = [];
  for (const f of delta.features) {
    if (!f.same) { features.push(f); continue } // geometría nueva/cambiada: viene completa
    const old = prevById.get(f.id);
    if (!old) continue; // `same` sin prev (no debería pasar): descartar (evita feature sin malla)
    // conserva la geometría anterior; sobrescribe solo lo VOLÁTIL que trae el delta
    features.push({
      ...old, rev: f.rev, name: f.name, color: f.color,
      visible: f.visible, group: f.group, is_guide: f.is_guide, // V6.2e Fix 7: guía es metadato
    });
  }
  const allDefs = { ...prev.definitions, ...delta.definitions };
  const definitions: Record<string, (typeof allDefs)[string]> = {};
  for (const f of features) {
    if (f.mesh_key && allDefs[f.mesh_key]) definitions[f.mesh_key] = allDefs[f.mesh_key];
  }
  return { features, definitions, document: delta.document, epoch: delta.epoch };
}

/** Ids de las piezas que un delta trae nuevas, con geometría nueva o ya no trae. */
export interface CambiosDelDelta {
  nuevos: string[];
  cambiados: string[];
  eliminados: string[];
}

/** Qué piezas cambió un delta respecto de `prev` (la escena ANTES de mergearlo).
 * - `nuevos`: vienen en el delta y no estaban en `prev`.
 * - `cambiados`: estaban y vuelven SIN `same`, es decir, con geometría nueva (su rev cambió).
 * - `eliminados`: estaban en `prev` y el delta ya no los trae.
 *
 * Marca GEOMETRÍA, no apariencia: una pieza `same` con nombre, color, visibilidad o grupo
 * distintos NO cuenta como cambiada (esos metadatos viajan en la entrada `same` sin subir el
 * rev). Una `same` sin prev tampoco cuenta: `mergeSceneDelta` la descarta y no llega a la
 * escena. Orden estable: el del delta para nuevos y cambiados, el de `prev` para eliminados. */
export function cambiosDelDelta(prev: SceneOut, delta: SceneOut): CambiosDelDelta {
  const antes = new Set(prev.features.map((f) => f.id));
  const ahora = new Set(delta.features.map((f) => f.id));
  const nuevos: string[] = [];
  const cambiados: string[] = [];
  for (const f of delta.features) {
    if (!antes.has(f.id)) { if (!f.same) nuevos.push(f.id); }
    else if (!f.same) cambiados.push(f.id);
  }
  const eliminados = prev.features.filter((f) => !ahora.has(f.id)).map((f) => f.id);
  return { nuevos, cambiados, eliminados };
}
