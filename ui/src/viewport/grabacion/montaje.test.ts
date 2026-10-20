import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { ACENTO, BRILLO_RESALTE, crearMontaje } from "./montaje";

/* El montaje del video en el visor (video-realista D5): las piezas entran tanda por tanda, lo
   que entra brilla con el acento y se apaga, una pieza oculta sigue oculta y al terminar cada
   malla vuelve a su material (el compartido nunca se toca) y a su visibilidad. */

function mallas() {
  const compartido = new THREE.MeshStandardMaterial({ color: 0x888888 });
  const m = new Map<string, THREE.Mesh>();
  for (const id of ["a", "b", "oculta"]) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10), compartido);
    mesh.position.x = id === "b" ? 100 : 0;
    m.set(id, mesh);
  }
  m.get("oculta")!.visible = false;
  return { m, compartido };
}

describe("montaje", () => {
  it("vacía, suma por tandas y completa sin tocar lo oculto", () => {
    const { m } = mallas();
    const mon = crearMontaje(m, ["a", "b", "oculta", "sin-malla"]);
    expect(mon.ids).toEqual(["a", "b"]);
    mon.vaciar();
    expect([...m.values()].map((x) => x.visible)).toEqual([false, false, false]);
    mon.sumar(["a"], 3);
    expect(m.get("a")!.visible).toBe(true);
    expect(m.get("b")!.visible).toBe(false);
    mon.completar();
    expect([...m.values()].map((x) => x.visible)).toEqual([true, true, false]);
  });

  it("lo que entra brilla con el acento, se apaga y deja el material compartido intacto", () => {
    const { m, compartido } = mallas();
    const mon = crearMontaje(m, ["a", "b"]);
    mon.vaciar();
    mon.sumar(["a"], 10);
    mon.resaltar(10, 10, 1.2);
    const copia = m.get("a")!.material as THREE.MeshStandardMaterial;
    expect(copia).not.toBe(compartido);
    expect(copia.emissive.equals(ACENTO)).toBe(true);
    expect(copia.emissiveIntensity).toBeCloseTo(BRILLO_RESALTE);
    expect(compartido.emissive.getHex()).toBe(0);
    mon.resaltar(16, 10, 1.2);
    expect(copia.emissiveIntensity).toBeCloseTo(BRILLO_RESALTE / 2);
    mon.resaltar(30, 10, 1.2);
    expect(m.get("a")!.material).toBe(compartido);
  });

  it("restaurar devuelve materiales y visibilidad aunque quede algo resaltado", () => {
    const { m, compartido } = mallas();
    const mon = crearMontaje(m, ["a", "b", "oculta"]);
    mon.vaciar();
    mon.sumar(["b"], 0);
    mon.restaurar();
    expect(m.get("b")!.material).toBe(compartido);
    expect([...m.values()].map((x) => x.visible)).toEqual([true, true, false]);
  });

  it("la caja es la de lo que se monta", () => {
    const { m } = mallas();
    const caja = crearMontaje(m, ["a", "b", "oculta"]).caja();
    expect(caja.min.x).toBeCloseTo(-5);
    expect(caja.max.x).toBeCloseTo(105);
  });
});
