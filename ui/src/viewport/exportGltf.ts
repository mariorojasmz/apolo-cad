import type { Group } from "three";

/* Export glTF (.glb) CLIENT-side: las mallas del viewport ya existen en three.js,
   así que el export no necesita backend. Se dispara con
   CustomEvent("apolo:export-gltf") (mismo patrón desacoplado que "apolo:fit");
   el TopBar lo emite desde el menú Archivo. GLTFExporter se importa dinámico
   (solo pesa al usarlo). */

export function installGltfExport(group: Group, projectName: () => string): () => void {
  const onExport = () => {
    void (async () => {
      const { GLTFExporter } = await import("three/examples/jsm/exporters/GLTFExporter.js");
      new GLTFExporter().parse(
        group,
        (result) => {
          const blob =
            result instanceof ArrayBuffer
              ? new Blob([result], { type: "model/gltf-binary" })
              : new Blob([JSON.stringify(result)], { type: "model/gltf+json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `${projectName() || "modelo"}.glb`;
          a.click();
          URL.revokeObjectURL(url);
        },
        (err) => console.error("Export glTF falló:", err),
        { binary: true },
      );
    })();
  };
  window.addEventListener("apolo:export-gltf", onExport);
  return () => window.removeEventListener("apolo:export-gltf", onExport);
}
