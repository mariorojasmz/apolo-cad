import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

/* Entorno de iluminación basado en imagen (IBL) generado proceduralmente con
   RoomEnvironment (sin assets externos -> compatible con CSP). Da a los metales
   algo que reflejar; sin esto el PBR queda lavado. Solo afecta a los reflejos
   (scene.environment), NO al fondo (se mantiene el clearColor oscuro). */
export function setupEnvironment(renderer: THREE.WebGLRenderer, scene: THREE.Scene): () => void {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  const envMap = pmrem.fromScene(room, 0.04).texture;
  scene.environment = envMap;

  return () => {
    scene.environment = null;
    envMap.dispose();
    pmrem.dispose();
    room.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      const mat = mesh.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
      else if (mat) mat.dispose();
    });
  };
}
