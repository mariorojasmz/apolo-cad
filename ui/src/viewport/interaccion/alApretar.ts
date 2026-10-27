import * as THREE from "three";

/* Qué hace apretar el botón sobre el visor (plan visor-para-evaluar D16): sobre una pieza, la
   agarra para moverla; si la máquina está en una POSE (la puerta del tablero abierta, una junta
   movida) o la pieza no se puede mover, sólo la SELECCIONA; sin pieza, o con Mayús/Ctrl, empieza
   el recuadro. Antes, en pose caía al recuadro: el clic quedaba en un recuadro de 0 px y no
   elegía nada en TODA la máquina mientras la puerta estuviera abierta. Puro, para vitest. */

export type AlApretar = "mover" | "seleccionar" | "recuadro";

export function queHaceElApretar(o: { pieza: boolean; modificador: boolean; posando: boolean; fija: boolean }): AlApretar {
  if (!o.pieza || o.modificador) return "recuadro";
  return o.posando || o.fija ? "seleccionar" : "mover";
}

/** Las 8 esquinas de una pieza en su pose VISTA (la malla, con la junta aplicada); sin malla, las
   de su caja de diseño. El recuadro elige con ellas: una puerta abierta se elige donde se ve. */
export function esquinasVistas(malla: THREE.Object3D | undefined, bbox: { min: number[]; max: number[] }): THREE.Vector3[] {
  const caja = malla
    ? new THREE.Box3().setFromObject(malla)
    : new THREE.Box3(new THREE.Vector3(bbox.min[0], bbox.min[1], bbox.min[2]), new THREE.Vector3(bbox.max[0], bbox.max[1], bbox.max[2]));
  const out: THREE.Vector3[] = [];
  for (const x of [caja.min.x, caja.max.x]) for (const y of [caja.min.y, caja.max.y]) for (const z of [caja.min.z, caja.max.z]) {
    out.push(new THREE.Vector3(x, y, z));
  }
  return out;
}

/** Lo que cruza el rayo, con cada malla en su pose VISTA: la pose de una junta (o una pieza
   animada) se escribe en `matrix` y su `matrixWorld` recién se pone al día al dibujar el próximo
   cuadro; elegir antes (o con el dibujo en pausa) usaría la pose anterior. Todo pick pasa por aquí. */
export function piezasBajo(raycaster: THREE.Raycaster, group: THREE.Object3D): THREE.Intersection[] {
  group.updateMatrixWorld();
  return raycaster.intersectObjects(group.children, false);
}
