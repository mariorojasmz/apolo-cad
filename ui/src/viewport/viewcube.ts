import * as THREE from "three";

/* ViewCube de navegación: cubo etiquetado en una esquina que gira en sincronía
   con la cámara principal; al hacer clic en una cara, reorienta la vista en esa
   dirección. Autocontenido (escena+cámara orto propias, renderizado en un
   viewport de esquina con scissor). No usa librerías externas. */

const PX = 96; // lado del recuadro en px (CSS)
const MARGIN = 10;

type Dir = [number, number, number];

// Caras de BoxGeometry en orden: +X, -X, +Y, -Y, +Z, -Z. Etiqueta + dirección
// de vista (normal exterior, que es la posición de cámara para esa vista).
const FACES: { label: string; dir: Dir }[] = [
  { label: "DER", dir: [1, 0, 0] },
  { label: "IZQ", dir: [-1, 0, 0] },
  { label: "ATRÁS", dir: [0, 1, 0] },
  { label: "FRENTE", dir: [0, -1, 0] },
  { label: "SUP", dir: [0, 0, 1] },
  { label: "INF", dir: [0, 0, -1] },
];

export interface ViewCube {
  render(renderer: THREE.WebGLRenderer, mainCamera: THREE.Camera): void;
  handleClick(e: MouseEvent, renderer: THREE.WebGLRenderer, onView: (dir: Dir) => void): boolean;
  dispose(): void;
}

function faceTexture(label: string): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = "#39404e";
  g.fillRect(0, 0, 128, 128);
  g.strokeStyle = "#5b6478";
  g.lineWidth = 8;
  g.strokeRect(0, 0, 128, 128);
  g.fillStyle = "#e6e9ef";
  g.font = "bold 20px Segoe UI, Arial, sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(label, 64, 64);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export function createViewCube(): ViewCube {
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1.4, 1.4, 1.4, -1.4, 0.1, 100);
  scene.add(new THREE.AmbientLight(0xffffff, 0.9));
  const keyLight = new THREE.DirectionalLight(0xffffff, 0.6);
  keyLight.position.set(2, 3, 4);
  scene.add(keyLight);

  const textures = FACES.map((f) => faceTexture(f.label));
  const materials = textures.map((map) => new THREE.MeshBasicMaterial({ map }));
  const cube = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), materials);
  scene.add(cube);

  const raycaster = new THREE.Raycaster();
  const tmp = new THREE.Vector3();

  function cornerRect(renderer: THREE.WebGLRenderer) {
    const size = renderer.getSize(new THREE.Vector2());
    return { size, x: size.x - PX - MARGIN, yBottom: size.y - PX - MARGIN };
  }

  return {
    render(renderer, mainCamera) {
      // la cámara del cubo orbita igual que la principal (cubo fijo a ejes mundo)
      mainCamera.getWorldDirection(tmp).negate().multiplyScalar(4);
      camera.position.copy(tmp);
      camera.up.copy(mainCamera.up);
      camera.lookAt(0, 0, 0);

      const { size, x, yBottom } = cornerRect(renderer);
      renderer.autoClear = false;
      renderer.clearDepth();
      renderer.setScissorTest(true);
      renderer.setViewport(x, yBottom, PX, PX);
      renderer.setScissor(x, yBottom, PX, PX);
      renderer.render(scene, camera);
      renderer.setScissorTest(false);
      renderer.setViewport(0, 0, size.x, size.y);
      renderer.autoClear = true;
    },

    handleClick(e, renderer, onView) {
      const rect = renderer.domElement.getBoundingClientRect();
      const { size, x } = cornerRect(renderer);
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top; // desde arriba
      const x0 = x;
      const x1 = x + PX;
      const y0 = MARGIN; // esquina superior derecha (en coords de pantalla, desde arriba)
      const y1 = MARGIN + PX;
      if (px < x0 || px > x1 || py < y0 || py > y1) return false; // fuera: sigue el picking normal

      const ndc = new THREE.Vector2(
        ((px - x0) / PX) * 2 - 1,
        -(((py - y0) / PX) * 2 - 1),
      );
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObject(cube, false);
      if (hits.length && hits[0].face) {
        const n = hits[0].face.normal; // cubo sin rotación => normal local == mundo
        onView([n.x, n.y, n.z]);
      }
      void size;
      return true; // dentro del recuadro: consume el clic
    },

    dispose() {
      cube.geometry.dispose();
      materials.forEach((m) => m.dispose());
      textures.forEach((t) => t.dispose());
    },
  };
}
