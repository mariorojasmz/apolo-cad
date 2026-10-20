import { describe, expect, it } from "vitest";
import * as THREE from "three";
import {
  ALCANCE_MIN_MM, aplicarEncuadre, crearPlano, crearProgramador, crearSombraContacto, encuadreSombra,
  HOLGURA_PLANO_MM, INTERVALO_MIN_MS, MARGEN_FRACCION, MARGEN_MIN_MM, type RendererSombra,
} from "./sombraContacto";

/* Sombra de contacto (plan piso-con-sombra, D2–D5): encuadre de la cámara ortográfica, altura
   del plano y la bandera `sucia`. El render de verdad necesita WebGL: aquí va con un renderer
   falso que sólo cuenta y mira qué estaba visible al dibujar la profundidad. */

const caja = (min: number[], max: number[]) =>
  new THREE.Box3(new THREE.Vector3(...min), new THREE.Vector3(...max));

describe("encuadreSombra", () => {
  it("cuadrado centrado en la planta, con margen, y el plano en el min.z", () => {
    const e = encuadreSombra(caja([0, -300, 120], [4000, 300, 1020]))!;
    expect(e.cx).toBe(2000);
    expect(e.cy).toBe(0);
    expect(e.z).toBeCloseTo(120 - HOLGURA_PLANO_MM);
    expect(e.lado).toBeCloseTo(4000 * (1 + 2 * MARGEN_FRACCION)); // el lado mayor manda: cuadrado
    expect(e.alcance).toBeGreaterThan(0);
    expect(e.alcance).toBeLessThan(900 + 1); // no ve más alto que la máquina
  });

  it("una pieza chica lleva el margen mínimo y el alcance mínimo", () => {
    const e = encuadreSombra(caja([0, 0, 0], [100, 50, 10]))!;
    expect(e.lado).toBeCloseTo(100 + 2 * MARGEN_MIN_MM);
    expect(e.alcance).toBeCloseTo(ALCANCE_MIN_MM + HOLGURA_PLANO_MM);
  });

  it("sin nada visible no hay encuadre", () => {
    expect(encuadreSombra(new THREE.Box3())).toBeNull();
  });
});

describe("aplicarEncuadre", () => {
  const e = encuadreSombra(caja([0, -300, 120], [4000, 300, 1020]))!;
  const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const plano = crearPlano(new THREE.MeshBasicMaterial());
  aplicarEncuadre(cam, plano, e);

  it("la cámara está en el plano y mira hacia arriba", () => {
    expect(cam.position.toArray()).toEqual([e.cx, e.cy, e.z]);
    const mira = cam.getWorldDirection(new THREE.Vector3());
    expect(mira.z).toBeCloseTo(1);
    expect(cam.right - cam.left).toBeCloseTo(e.lado);
    expect(cam.far).toBeCloseTo(e.alcance);
  });

  it("lo que está apoyado en el piso cae dentro del frustum; lo que pasa el alcance, fuera", () => {
    const pata = new THREE.Vector3(10, -290, 120).project(cam);
    expect(Math.abs(pata.x)).toBeLessThan(1);
    expect(Math.abs(pata.y)).toBeLessThan(1);
    expect(pata.z).toBeGreaterThanOrEqual(-1);
    expect(pata.z).toBeLessThan(-0.99); // pegada al piso → profundidad ≈ 0 (sombra plena)
    expect(new THREE.Vector3(2000, 0, 120 + e.alcance + 50).project(cam).z).toBeGreaterThan(1);
  });

  it("la textura cae en su sitio: el UV del plano coincide con lo que ve la cámara", () => {
    plano.updateMatrixWorld();
    const pos = plano.geometry.getAttribute("position");
    const uv = plano.geometry.getAttribute("uv");
    for (let i = 0; i < pos.count; i++) {
      const mundo = new THREE.Vector3().fromBufferAttribute(pos, i).applyMatrix4(plano.matrixWorld);
      mundo.z += 1; // apenas sobre el plano, dentro del frustum
      const ndc = mundo.project(cam);
      expect((ndc.x + 1) / 2).toBeCloseTo(uv.getX(i)); // u de la textura del render target
      expect((ndc.y + 1) / 2).toBeCloseTo(uv.getY(i)); // v (0 abajo de la imagen)
    }
  });
});

describe("crearProgramador (bandera sucia)", () => {
  it("nace sucia, calcula una vez y en reposo no vuelve a calcular", () => {
    const p = crearProgramador();
    expect(p.toca(0, false)).toBe(true);
    let n = 0;
    for (let t = 16; t < 5000; t += 16) if (p.toca(t, false)) n++;
    expect(n).toBe(0);
  });

  it("al marcarla recalcula una vez; lo pedido muy seguido queda pendiente, no se pierde", () => {
    const p = crearProgramador();
    p.toca(0, false);
    p.marcar();
    expect(p.toca(1000, false)).toBe(true);
    p.marcar();
    expect(p.toca(1000 + INTERVALO_MIN_MS / 2, false)).toBe(false); // demasiado pronto
    expect(p.toca(1000 + INTERVALO_MIN_MS, false)).toBe(true); // pendiente → ahora
    expect(p.toca(1000 + 3 * INTERVALO_MIN_MS, false)).toBe(false);
  });

  it("durante un arrastre, como mucho a 10 Hz; al soltar, una pasada final", () => {
    const p = crearProgramador();
    p.toca(0, false);
    let n = 0;
    for (let t = 1000; t < 2000; t += 16) if (p.toca(t, true)) n++;
    expect(n).toBeGreaterThanOrEqual(9);
    expect(n).toBeLessThanOrEqual(10);
    expect(p.toca(2200, false)).toBe(true); // fin del arrastre
    expect(p.toca(2400, false)).toBe(false);
  });
});

describe("crearSombraContacto", () => {
  const armar = () => {
    const scene = new THREE.Scene();
    const ground = new THREE.Mesh();
    const grid = new THREE.Object3D();
    const luz = new THREE.DirectionalLight();
    const group = new THREE.Group();
    const pata = new THREE.Mesh(new THREE.BoxGeometry(50, 50, 400));
    pata.position.set(0, 0, 200);
    group.add(pata);
    scene.add(luz, ground, grid, group);
    const visiblesAlDibujar: string[][] = [];
    let destino: unknown = null;
    const renderer = {
      shadowMap: { autoUpdate: true, needsUpdate: false },
      getRenderTarget: () => destino,
      setRenderTarget: (rt: unknown) => { destino = rt; },
      clear: () => {},
      getClearColor: (c: THREE.Color) => c.set(0x1b1e24),
      getClearAlpha: () => 0,
      setClearColor: () => {},
      render: (obj: THREE.Object3D) => {
        if (obj === scene) visiblesAlDibujar.push(scene.children.filter((o) => o.visible).map((o) => o.type));
      },
    } as unknown as RendererSombra;
    const sombra = crearSombraContacto(renderer, scene, group, ground);
    return { scene, ground, grid, group, pata, sombra, visiblesAlDibujar, renderer };
  };

  it("no recalcula en reposo; sí tras reconstruir mallas o mover una pose", () => {
    const { sombra } = armar();
    sombra.actualizar(0, false);
    expect(sombra.recalculos()).toBe(1);
    for (let t = 16; t < 3000; t += 16) sombra.actualizar(t, false);
    expect(sombra.recalculos()).toBe(1); // reposo: costo cero
    sombra.fijarPlanos([]); // lo que hace el efecto de reconstruir mallas
    sombra.actualizar(3000, false);
    expect(sombra.recalculos()).toBe(2);
    sombra.marcarSucia(); // lo que hace el efecto de pose cinemática
    sombra.actualizar(3200, false);
    expect(sombra.recalculos()).toBe(3);
  });

  it("dibuja la profundidad sólo de las piezas (y las luces) y deja la escena como estaba", () => {
    const { scene, sombra, visiblesAlDibujar, renderer } = armar();
    sombra.actualizar(0, false);
    expect(visiblesAlDibujar).toEqual([["DirectionalLight", "Group"]]);
    expect(scene.children.every((o) => o.visible)).toBe(true); // el plano de la sombra también
    expect(scene.overrideMaterial).toBeNull();
    expect(renderer.shadowMap.autoUpdate).toBe(true);
    expect(renderer.getRenderTarget()).toBeNull();
  });

  it("el plano se apoya en el min.z de lo visible y se oculta con el suelo", () => {
    const { scene, ground, pata, sombra } = armar();
    sombra.actualizar(0, false);
    const plano = scene.children[scene.children.length - 1];
    expect(plano.position.z).toBeCloseTo(-HOLGURA_PLANO_MM);
    pata.position.z = 700; // la pata sube: el piso de la máquina queda en 500
    sombra.marcarSucia();
    sombra.actualizar(1000, false);
    expect(plano.position.z).toBeCloseTo(500 - HOLGURA_PLANO_MM);
    ground.visible = false;
    sombra.actualizar(1016, false);
    expect(plano.visible).toBe(false);
  });

  it("sin piezas visibles no hay sombra", () => {
    const { scene, group, sombra } = armar();
    group.clear();
    sombra.actualizar(0, false);
    expect(scene.children[scene.children.length - 1].visible).toBe(false);
  });
});
