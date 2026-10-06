import * as THREE from "three";
import { OutlinePass } from "three/examples/jsm/postprocessing/OutlinePass.js";
import { useVisor } from "../visor/estado";

/* Destello de las piezas que cambió el agente (plan modo-visor, D8): un SEGUNDO OutlinePass,
   verde, cuya intensidad late y se apaga a los ~3 s de `useVisor().pulso` («Ver» lo reinicia).
   Contorno y NO tinte `emissive` (ui/CLAUDE.md § Viewport: el tinte rojizo significa guardado
   fallido). Va en el composer después del contorno de selección y antes del OutputPass, y vale
   en los dos modos, Visor y Completo. Las mallas se recolectan cada frame desde la store del
   visor, igual que la selección desde `selectionRef`: robusto a que el rebuild reemplace la
   malla de una pieza marcada (que es justo lo que pasa cuando cambia). */

/** Cuánto dura el destello desde el pulso (ms). */
export const DURACION_DESTELLO_MS = 3000;
const LATIDO_MS = 1000; // un latido por segundo: tres en total
const COLA_MS = 600; // el último tramo se apaga suave
const FUERZA = 6; // edgeStrength a intensidad 1 (el contorno de selección usa 4)
const VERDE = 0x46b58a; // --ok de styles.css
const VERDE_TAPADO = 0x1f5a43; // la parte del contorno que tapa otra pieza: tenue

/** Intensidad del contorno (0–1) a `t` ms del pulso: arranca encendido, late cada `LATIDO_MS`
   sin llegar a apagarse y se desvanece en los últimos `COLA_MS`. 0 antes del pulso y después
   de `DURACION_DESTELLO_MS`. */
export function intensidadDestello(t: number): number {
  if (!(t >= 0 && t < DURACION_DESTELLO_MS)) return 0;
  const latido = 0.5 + 0.5 * Math.cos((2 * Math.PI * t) / LATIDO_MS);
  const cola = Math.min(1, (DURACION_DESTELLO_MS - t) / COLA_MS);
  return (0.35 + 0.65 * latido) * cola;
}

export interface Destello {
  /** El pass a agregar al composer (entre el contorno de selección y el OutputPass). */
  pass: OutlinePass;
  /** Por frame: recolecta las mallas marcadas y ajusta la intensidad; sin destello vivo,
     apaga el pass (el composer se lo salta). `ahora` en ms de `Date.now()`, como `pulso`. */
  actualizar: (meshes: ReadonlyMap<string, THREE.Object3D>, ahora: number) => void;
  dispose: () => void;
}

export function crearDestello(scene: THREE.Scene, camera: THREE.Camera): Destello {
  const pass = new OutlinePass(new THREE.Vector2(1, 1), scene, camera);
  pass.edgeGlow = 0.6; // un halo leve: se lee como «destello», no como selección
  pass.edgeThickness = 1.5;
  pass.pulsePeriod = 0; // el latido lo da `intensidadDestello`, con fin
  pass.visibleEdgeColor.set(VERDE);
  pass.hiddenEdgeColor.set(VERDE_TAPADO);
  pass.enabled = false;
  const marcadas: THREE.Object3D[] = []; // buffer reusado por frame (sin asignaciones)
  return {
    pass,
    actualizar: (meshes, ahora) => {
      const { marcados, pulso } = useVisor.getState();
      const k = marcados.length ? intensidadDestello(ahora - pulso) : 0;
      marcadas.length = 0;
      if (k > 0) for (const id of marcados) { const m = meshes.get(id); if (m) marcadas.push(m); }
      pass.selectedObjects = marcadas;
      pass.edgeStrength = FUERZA * k;
      pass.enabled = marcadas.length > 0;
    },
    dispose: () => pass.dispose(),
  };
}
