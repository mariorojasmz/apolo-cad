import * as THREE from "three";

/* Overlay de la última medida (línea + dos puntos, ámbar, siempre encima). Salió de
   Viewport.tsx sin cambiar la lógica (plan piso-con-sombra, F1). */

export function objetoMedida(measure: { p1: number[]; p2: number[] }): THREE.Group {
  const a = new THREE.Vector3(...(measure.p1 as [number, number, number]));
  const b = new THREE.Vector3(...(measure.p2 as [number, number, number]));
  const group = new THREE.Group();
  group.add(
    new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([a, b]),
      new THREE.LineBasicMaterial({ color: 0xffc04d, depthTest: false }),
    ),
  );
  for (const p of [a, b]) {
    const dot = new THREE.Mesh(
      new THREE.SphereGeometry(4, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0xffc04d, depthTest: false }),
    );
    dot.position.copy(p);
    group.add(dot);
  }
  group.renderOrder = 99;
  return group;
}
