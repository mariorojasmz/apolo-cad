import * as THREE from "three";
import { useTablero } from "./estado";
import { recorridoDe } from "./vista";

/* El recorrido de UN conductor en el 3D (plan V8.5 D13): un tubo fino por las canaletas, sólo
   mientras está elegido en el panel «Tablero». Va en la escena, fuera del grupo de piezas: no se
   elige con el clic, no oscurece la oclusión ambiental ni entra a la sombra. Se ve a través de la
   canaleta (sin prueba de profundidad): el 3D señala DÓNDE pasa; el estado vive en el panel, así
   que el color es el acento del tema, nunca uno de estado. */

/** El grosor del tubo y de los extremos, en mm (un conductor de 1,5 mm² mide ≈ 3 mm). */
const RADIO_MM = 1.6;
const EXTREMO_MM = 3.2;

/** Un color del tema (`--accent`), leído del CSS; sin DOM, el respaldo. */
export function colorDelTema(nombre: string, respaldo: string): string {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
    return v || respaldo;
  } catch {
    return respaldo;
  }
}

/** Las polilíneas como tubos (una curva por tramo, sin tramos de largo cero) y una bolita en
   cada extremo. El llamador lo agrega a la escena y lo libera con `liberarRecorrido`. */
export function tuboDeRecorrido(tramos: readonly (readonly number[])[][], color: THREE.ColorRepresentation): THREE.Group {
  const g = new THREE.Group();
  g.name = "recorrido-conductor";
  g.renderOrder = 10;
  const material = new THREE.MeshBasicMaterial({ color, depthTest: false, depthWrite: false, transparent: true, opacity: 0.95 });
  const sinRayo = () => {}; // el clic atraviesa el recorrido hasta la pieza
  for (const tramo of tramos) {
    const pts = tramo.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
    const camino = new THREE.CurvePath<THREE.Vector3>();
    for (let i = 0; i + 1 < pts.length; i++) {
      if (pts[i].distanceTo(pts[i + 1]) > 1e-3) camino.add(new THREE.LineCurve3(pts[i], pts[i + 1]));
    }
    if (!camino.curves.length) continue;
    const tubo = new THREE.Mesh(new THREE.TubeGeometry(camino, Math.max(8, camino.curves.length * 4), RADIO_MM, 8, false), material);
    tubo.raycast = sinRayo;
    tubo.renderOrder = 10;
    g.add(tubo);
    for (const p of [pts[0], pts[pts.length - 1]]) {
      const bola = new THREE.Mesh(new THREE.SphereGeometry(EXTREMO_MM, 16, 12), material);
      bola.position.copy(p);
      bola.raycast = sinRayo;
      bola.renderOrder = 10;
      g.add(bola);
    }
  }
  return g;
}

export function liberarRecorrido(g: THREE.Group): void {
  const materiales = new Set<THREE.Material>();
  g.traverse((o) => {
    if (o instanceof THREE.Mesh) {
      o.geometry.dispose();
      materiales.add(o.material as THREE.Material);
    }
  });
  for (const m of materiales) m.dispose();
  g.removeFromParent();
}

/** Dibuja en `scene` el recorrido del conductor elegido en el panel y lo sigue. → limpieza. */
export function instalarRecorrido(ctx: { scene: THREE.Scene }): () => void {
  let actual: THREE.Group | null = null;
  let clave: number[][][] | null = null;
  const pintar = () => {
    const st = useTablero.getState();
    const tramos = recorridoDe(st.panel, st.conductor);
    if (tramos === clave) return;
    clave = tramos;
    if (actual) liberarRecorrido(actual);
    actual = null;
    if (tramos) {
      actual = tuboDeRecorrido(tramos, colorDelTema("--accent", "#5b8cff"));
      ctx.scene.add(actual);
    }
  };
  pintar();
  const dejar = useTablero.subscribe(pintar);
  return () => {
    dejar();
    if (actual) liberarRecorrido(actual);
    actual = null;
  };
}
