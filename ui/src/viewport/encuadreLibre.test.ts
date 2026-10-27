import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { AREA_COMPLETA, aNdc, areaLibre } from "./areaLibre";
import { crearAtenuador, OPACIDAD_ATENUADA } from "./atenuar";
import { destinoEncuadre } from "./camara";
import {
  cajaConApertura, direccionFrente, elegirVista, normalDominante, poseEnArea, queTapa, vistasCandidatas,
} from "./encuadreLibre";

/* El encuadre que se ve (plan visor-para-evaluar D13–D15): el área libre sin el panel lateral, el
   frente de una pieza y lo que tapa. */

const lienzo = { left: 0, top: 0, right: 1000, bottom: 600 };

describe("areaLibre", () => {
  it("un cajón a la derecha recorta ese lado; uno a la izquierda, el otro", () => {
    expect(areaLibre(lienzo, [{ left: 640, top: 60, right: 990, bottom: 560 }])).toEqual({ ...lienzo, right: 640 });
    expect(areaLibre(lienzo, [{ left: 10, top: 10, right: 300, bottom: 590 }])).toEqual({ ...lienzo, left: 300 });
  });
  it("una tapa chica (un menú) no cuenta; sin tapas, el lienzo entero", () => {
    expect(areaLibre(lienzo, [{ left: 700, top: 500, right: 900, bottom: 590 }])).toEqual(lienzo);
    expect(areaLibre(lienzo, [])).toEqual(lienzo);
  });
  it("si lo libre queda muy angosto (pantalla de teléfono), se queda el lienzo", () => {
    expect(areaLibre(lienzo, [{ left: 150, top: 0, right: 1000, bottom: 600 }])).toEqual(lienzo);
  });
  it("aNdc: el lienzo entero es −1…1 y la mitad izquierda, −1…0", () => {
    expect(aNdc(lienzo, lienzo)).toEqual(AREA_COMPLETA);
    expect(aNdc(lienzo, { ...lienzo, right: 500 })).toEqual({ x0: -1, x1: 0, y0: -1, y1: 1 });
  });
});

const camara = { fov: 50, aspect: 1000 / 600, up: new THREE.Vector3(0, 0, 1) };
const caja = new THREE.Box3(new THREE.Vector3(-100, -100, 0), new THREE.Vector3(100, 100, 400));

/** Dónde cae `p` en la pantalla de la cámara en `pose` (coordenadas normalizadas). */
function proyectar(pose: { posicion: THREE.Vector3; objetivo: THREE.Vector3 }, p: THREE.Vector3): THREE.Vector3 {
  const cam = new THREE.PerspectiveCamera(camara.fov, camara.aspect, 1, 1e6);
  cam.up.copy(camara.up);
  cam.position.copy(pose.posicion);
  cam.lookAt(pose.objetivo);
  cam.updateMatrixWorld();
  return p.clone().project(cam);
}

describe("poseEnArea", () => {
  const dir = new THREE.Vector3(1, -1, 0.8);
  it("con el área completa da la misma pose de siempre", () => {
    const a = poseEnArea(caja, dir, camara)!;
    const b = destinoEncuadre(dir.clone(), new THREE.Vector3(), caja)!;
    expect(a.posicion.distanceTo(b.posicion)).toBeLessThan(1e-6);
    expect(a.objetivo.distanceTo(b.objetivo)).toBeLessThan(1e-6);
  });
  it("con el panel a la derecha, la caja queda en el centro de lo que se ve y la cámara se aleja", () => {
    const area = aNdc(lienzo, { ...lienzo, right: 450 });
    const pose = poseEnArea(caja, dir, camara, area)!;
    const centro = proyectar(pose, caja.getCenter(new THREE.Vector3()));
    expect(centro.x).toBeCloseTo((area.x0 + area.x1) / 2, 5);
    expect(centro.y).toBeCloseTo(0, 5);
    const lejos = pose.posicion.distanceTo(pose.objetivo);
    const siempre = poseEnArea(caja, dir, camara)!;
    expect(lejos).toBeGreaterThan(siempre.posicion.distanceTo(siempre.objetivo));
    // toda la caja cae a la izquierda del panel
    for (const x of [caja.min.x, caja.max.x]) for (const y of [caja.min.y, caja.max.y]) for (const z of [caja.min.z, caja.max.z]) {
      expect(proyectar(pose, new THREE.Vector3(x, y, z)).x).toBeLessThan(area.x1);
    }
  });
});

/** Una placa (puerta) de 600 × 800 en el plano XZ, 20 mm de espesor, frente hacia −Y. */
function puerta(y = -310): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.BoxGeometry(600, 20, 800));
  m.position.set(0, y, 400);
  m.userData.featureId = "c1_puerta";
  return m;
}

describe("frente", () => {
  it("la normal dominante de una placa es la de sus caras grandes", () => {
    const n = normalDominante(puerta())!;
    expect(Math.abs(n.y)).toBeCloseTo(1, 5);
  });
  it("la dirección del frente apunta hacia afuera del gabinete, aunque la cámara esté detrás", () => {
    const gabinete = new THREE.Box3(new THREE.Vector3(-300, -300, 0), new THREE.Vector3(300, 300, 800));
    const d = direccionFrente(puerta(), gabinete, new THREE.Vector3(0, 5000, 400))!;
    expect(d.y).toBeCloseTo(-1, 5);
  });
  it("con la puerta ya abierta (la junta aplicada), se mira por su cara CERRADA", () => {
    const m = puerta();
    m.updateMatrix();
    m.userData.baseMatrix = m.matrix.clone(); // la pose de diseño, como `meshes.ts`
    m.matrixAutoUpdate = false; // la junta la gira 110° sobre Z (como `applyKinematicPoses`)
    m.matrix.premultiply(new THREE.Matrix4().makeRotationZ(THREE.MathUtils.degToRad(110)));
    m.updateMatrixWorld(true);
    const gabinete = new THREE.Box3(new THREE.Vector3(-300, -300, 0), new THREE.Vector3(300, 300, 800));
    expect(direccionFrente(m, gabinete, new THREE.Vector3(0, 5000, 400))!.y).toBeCloseTo(-1, 5);
  });
  it("la caja crece por delante lo que la puerta abre, y un tercio a los lados", () => {
    const gabinete = new THREE.Box3(new THREE.Vector3(-300, -300, 0), new THREE.Vector3(300, 300, 800));
    const c = cajaConApertura(gabinete, new THREE.Box3().setFromObject(puerta()), new THREE.Vector3(0, -1, 0));
    expect(c.min.y).toBeLessThan(gabinete.min.y - 700);
    expect(c.max.y).toBeCloseTo(gabinete.max.y + 800 / 3, 6);
    expect(c.min.x).toBeCloseTo(gabinete.min.x - 800 / 3, 6);
  });
});

describe("lo que tapa", () => {
  const gabinete = new THREE.Box3(new THREE.Vector3(-300, -300, 0), new THREE.Vector3(300, 300, 800));
  const dentro = new THREE.Mesh(new THREE.BoxGeometry(100, 100, 100));
  dentro.position.set(0, 0, 400);
  dentro.userData.featureId = "contactor";
  const muro = new THREE.Mesh(new THREE.BoxGeometry(3000, 50, 3000));
  muro.position.set(0, -800, 400);
  muro.userData.featureId = "guarda";
  for (const m of [dentro, muro]) m.updateMatrixWorld();

  it("una pieza entre la cámara y el gabinete tapa; lo de adentro y lo propio, no", () => {
    const r = queTapa(new THREE.Vector3(0, -4000, 400), gabinete, [dentro, muro], new Set(["c1_gabinete"]));
    expect(r.ids).toEqual(["guarda"]);
    expect(queTapa(new THREE.Vector3(0, -4000, 400), gabinete, [dentro], new Set()).ids).toEqual([]);
  });
  it("las vistas candidatas empiezan por la pedida y giran sobre «arriba»", () => {
    const v = vistasCandidatas(new THREE.Vector3(0, -1, 0), camara.up);
    expect(v[0].toArray()).toEqual([0, -1, 0]);
    expect(v[1].z).toBeCloseTo(0, 6);
    expect(v[3].z).toBeGreaterThan(0.3);
  });
  it("si una vista cercana está libre, la elige; si no, la pedida con lo que hay que atenuar", () => {
    const corto = new THREE.Mesh(new THREE.BoxGeometry(150, 50, 900)); // un poste: tapa sólo el frente exacto
    corto.position.set(0, -800, 400);
    corto.userData.featureId = "guarda corta";
    corto.updateMatrixWorld();
    const libre = elegirVista(gabinete, gabinete, new THREE.Vector3(0, -1, 0), camara, AREA_COMPLETA, [corto], new Set())!;
    expect(libre.atenuar).toEqual([]);
    expect(libre.pose.posicion.clone().sub(libre.pose.objetivo).normalize().y).toBeGreaterThan(-0.99);
    const tapada = elegirVista(gabinete, gabinete, new THREE.Vector3(0, -1, 0), camara, AREA_COMPLETA, [muro], new Set())!;
    expect(tapada.atenuar).toEqual(["guarda"]);
    expect(tapada.pose.posicion.clone().sub(tapada.pose.objetivo).normalize().y).toBeCloseTo(-1, 6);
  });
});

describe("atenuar", () => {
  it("deja translúcido lo que tapa y lo devuelve como estaba", () => {
    const mat = new THREE.MeshStandardMaterial({ opacity: 1 });
    const m = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), mat);
    m.userData.featureId = "guarda";
    const a = crearAtenuador();
    a.atenuar([m]);
    expect(mat.opacity).toBe(OPACIDAD_ATENUADA);
    expect(mat.transparent).toBe(true);
    expect(mat.depthWrite).toBe(false);
    expect(a.ids()).toEqual(["guarda"]);
    a.restaurar();
    expect(mat.opacity).toBe(1);
    expect(mat.transparent).toBe(false);
    expect(mat.depthWrite).toBe(true);
  });
});
