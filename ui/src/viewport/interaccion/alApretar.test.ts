import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { esquinasVistas, piezasBajo, queHaceElApretar } from "./alApretar";

/* Con la puerta del tablero abierta no se podía elegir NINGUNA pieza de la máquina (plan
   visor-para-evaluar D16): en pose, apretar sobre una pieza caía al recuadro (0 px, nada). */

describe("queHaceElApretar", () => {
  const base = { pieza: true, modificador: false, posando: false, fija: false };
  it("sobre una pieza la agarra; en pose (la puerta abierta) la selecciona, no hace un recuadro", () => {
    expect(queHaceElApretar(base)).toBe("mover");
    expect(queHaceElApretar({ ...base, posando: true })).toBe("seleccionar");
    expect(queHaceElApretar({ ...base, fija: true })).toBe("seleccionar");
  });
  it("sin pieza o con Mayús/Ctrl, el recuadro de siempre", () => {
    expect(queHaceElApretar({ ...base, pieza: false })).toBe("recuadro");
    expect(queHaceElApretar({ ...base, pieza: false, posando: true })).toBe("recuadro");
    expect(queHaceElApretar({ ...base, modificador: true })).toBe("recuadro");
  });
});

describe("esquinasVistas", () => {
  it("una pieza posada (la puerta girada) se elige donde se ve, no en su caja de diseño", () => {
    const puerta = new THREE.Mesh(new THREE.BoxGeometry(600, 20, 800));
    puerta.position.set(0, -310, 400);
    const diseno = { min: [-300, -320, 0], max: [300, -300, 800] };
    // la junta la gira 90° sobre su bisagra vertical (como `applyKinematicPoses`: matriz directa)
    const bisagra = new THREE.Matrix4().makeTranslation(-300, -310, 0)
      .multiply(new THREE.Matrix4().makeRotationZ(-Math.PI / 2))
      .multiply(new THREE.Matrix4().makeTranslation(300, 310, 0));
    puerta.updateMatrix();
    puerta.matrixAutoUpdate = false;
    puerta.matrix.premultiply(bisagra);
    puerta.updateMatrixWorld(true);
    const vistas = esquinasVistas(puerta, diseno);
    const ys = vistas.map((v) => v.y);
    expect(Math.min(...ys)).toBeLessThan(-800); // abierta: sobresale 600 mm hacia afuera
    const sinMalla = esquinasVistas(undefined, diseno);
    expect(Math.min(...sinMalla.map((v) => v.y))).toBe(-320);
  });
});

describe("piezasBajo", () => {
  it("elige la pieza en la pose que se ve aunque todavía no se haya dibujado el cuadro", () => {
    const group = new THREE.Group();
    const m = new THREE.Mesh(new THREE.BoxGeometry(100, 100, 100));
    m.userData.featureId = "puerta";
    group.add(m);
    group.updateMatrixWorld(true);
    // la junta la corre 1000 mm (como `applyKinematicPoses`: matrix a mano, sin dibujar)
    m.matrixAutoUpdate = false;
    m.matrix.makeTranslation(1000, 0, 0);
    m.matrixWorldNeedsUpdate = true;
    const r = new THREE.Raycaster(new THREE.Vector3(1000, -5000, 0), new THREE.Vector3(0, 1, 0));
    expect(piezasBajo(r, group).map((h) => h.object.userData.featureId)).toContain("puerta");
    const viejo = new THREE.Raycaster(new THREE.Vector3(0, -5000, 0), new THREE.Vector3(0, 1, 0));
    expect(piezasBajo(viejo, group)).toEqual([]); // donde estaba ya no hay nada
  });
});
