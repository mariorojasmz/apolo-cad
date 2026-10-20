import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as THREE from "three";
import type { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { CLAVE_LOCAL, gpuFloja, useCalidad } from "./calidad";
import { GtaoMaquina, INTERVALO_AJUSTE_MS, MSAA, crearCalidadVista, escalaOclusion } from "./calidadVista";
import { DISTANCIA, SOFTBOXES, crearEstudio, grisSala } from "./estudio";
import { LIGHT_OFFSET } from "./scene-setup";

/* La calidad del visor (video-realista D1): el interruptor, el estudio procedural y los pases
   de la calidad «alta». Sin GPU: se prueba la lógica (qué se prende, qué ve el GTAO, la escala). */

describe("interruptor de calidad", () => {
  let guardado: Record<string, string>;
  beforeEach(() => {
    guardado = {};
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => guardado[k] ?? null,
      setItem: (k: string, v: string) => { guardado[k] = v; },
    });
    useCalidad.setState({ calidad: "alta" });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("reconoce las GPU integradas o por software", () => {
    expect(gpuFloja("ANGLE (Intel, Intel(R) UHD Graphics (0x0000A721) Direct3D11 vs_5_0 ps_5_0, D3D11)")).toBe(true);
    expect(gpuFloja("Google SwiftShader")).toBe(true);
    expect(gpuFloja("llvmpipe (LLVM 15.0.7, 256 bits)")).toBe(true);
    expect(gpuFloja("ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)")).toBe(false);
    expect(gpuFloja("ANGLE (Intel, Intel(R) Arc(TM) A770 Graphics Direct3D11)")).toBe(false);
    expect(gpuFloja(null)).toBe(false);
  });

  it("una GPU floja arranca en «normal» sólo si nadie eligió", () => {
    useCalidad.getState().sugerirPorGpu("Intel(R) UHD Graphics");
    expect(useCalidad.getState().calidad).toBe("normal");
    useCalidad.getState().fijar("alta"); // la persona elige: se recuerda
    expect(guardado[CLAVE_LOCAL]).toBe("alta");
    useCalidad.getState().sugerirPorGpu("Intel(R) UHD Graphics");
    expect(useCalidad.getState().calidad).toBe("alta");
  });

  it("una GPU dedicada se queda en «alta»", () => {
    useCalidad.getState().sugerirPorGpu("NVIDIA GeForce RTX 4070 Ti");
    expect(useCalidad.getState().calidad).toBe("alta");
  });

  it("sin almacenamiento la elección igual cambia", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => { throw new Error("bloqueado"); },
      setItem: () => { throw new Error("bloqueado"); },
    });
    useCalidad.getState().fijar("normal");
    expect(useCalidad.getState().calidad).toBe("normal");
  });
});

describe("estudio procedural", () => {
  it("la sala es más clara en el horizonte que en el cenit y el piso", () => {
    expect(grisSala(0)).toBeGreaterThan(grisSala(1));
    expect(grisSala(0)).toBeGreaterThan(grisSala(-1));
    for (const z of [-1, -0.5, 0, 0.5, 1]) expect(grisSala(z)).toBeGreaterThan(0);
  });

  it("cuatro softboxes que brillan más que la sala y miran a la máquina", () => {
    const escena = crearEstudio();
    const paneles = escena.children.filter((o) => o.name in SOFTBOXES) as THREE.Mesh[];
    expect(paneles.map((p) => p.name).sort()).toEqual(["cenital", "contorno", "principal", "relleno"]);
    for (const p of paneles) {
      expect(p.position.length()).toBeCloseTo(DISTANCIA, 5);
      expect((p.material as THREE.MeshBasicMaterial).color.r).toBeGreaterThan(1); // emisivo
      // el panel mira al centro: su normal (+Z local) apunta hacia el origen
      p.updateMatrixWorld();
      const normal = new THREE.Vector3(0, 0, 1).transformDirection(p.matrixWorld);
      expect(normal.dot(p.position.clone().negate().normalize())).toBeGreaterThan(0.99);
    }
  });

  it("la luz principal viene del mismo lado que la direccional", () => {
    const principal = new THREE.Vector3(...SOFTBOXES.principal.dir).normalize();
    expect(principal.dot(LIGHT_OFFSET.clone().normalize())).toBeGreaterThan(0.95);
    expect(SOFTBOXES.principal.intensidad).toBeGreaterThan(SOFTBOXES.relleno.intensidad);
  });
});

describe("pases de la calidad alta", () => {
  beforeEach(() => {
    // SMAAPass carga sus tablas como imágenes: en node no hay Image
    vi.stubGlobal("Image", class { src = ""; onload: (() => void) | null = null; });
  });
  afterEach(() => vi.unstubAllGlobals());

  function escenaDePrueba() {
    const scene = new THREE.Scene();
    const group = new THREE.Group();
    const caja = new THREE.Mesh(new THREE.BoxGeometry(1000, 600, 800), new THREE.MeshStandardMaterial());
    caja.add(new THREE.LineSegments(new THREE.EdgesGeometry(caja.geometry)));
    group.add(caja);
    const piso = new THREE.Mesh(new THREE.PlaneGeometry(1, 1));
    const grilla = new THREE.GridHelper(10, 10);
    scene.add(group, piso, grilla);
    return { scene, group, caja, piso, grilla };
  }

  it("el radio de la oclusión sigue el tamaño de la máquina, con mínimo", () => {
    expect(escalaOclusion(4000).radio).toBeCloseTo(80);
    expect(escalaOclusion(4000).grosor).toBeCloseTo(40);
    expect(escalaOclusion(10).radio).toBeGreaterThan(0);
  });

  it("el GTAO sólo ve las piezas de la máquina, sin aristas, y después restaura", () => {
    const { scene, group, caja, piso, grilla } = escenaDePrueba();
    const oculto = new THREE.Mesh(); // algo ya oculto antes: debe seguir oculto
    oculto.visible = false;
    scene.add(oculto);
    const gtao = new GtaoMaquina(scene, new THREE.PerspectiveCamera(), group);
    gtao.overrideVisibility();
    expect(group.visible && caja.visible).toBe(true);
    expect(piso.visible || grilla.visible).toBe(false);
    expect(caja.children[0].visible).toBe(false); // aristas fuera
    gtao.restoreVisibility();
    expect(piso.visible && grilla.visible && caja.children[0].visible).toBe(true);
    expect(oculto.visible).toBe(false);
  });

  it("«alta» prende GTAO y SMAA sin MSAA; «normal» vuelve al visor de antes", () => {
    const { scene, group } = escenaDePrueba();
    const composer = {
      renderTarget1: new THREE.WebGLRenderTarget(1, 1, { samples: 4 }),
      renderTarget2: new THREE.WebGLRenderTarget(1, 1, { samples: 4 }),
    } as unknown as EffectComposer;
    const cv = crearCalidadVista(scene, new THREE.PerspectiveCamera(), group, composer);
    cv.fijar("alta");
    expect([cv.gtao.enabled, cv.smaa.enabled]).toEqual([true, true]);
    expect(composer.renderTarget1.samples).toBe(MSAA.alta);
    expect(composer.renderTarget2.samples).toBe(MSAA.alta);
    cv.fijar("normal");
    expect([cv.gtao.enabled, cv.smaa.enabled]).toEqual([false, false]);
    expect(composer.renderTarget1.samples).toBe(4);
    expect(cv.calidad()).toBe("normal");
  });

  it("ajustar escala el radio a la máquina, copia los planos de sección y respeta su tope", () => {
    const { scene, group, caja } = escenaDePrueba();
    const composer = {
      renderTarget1: new THREE.WebGLRenderTarget(1, 1), renderTarget2: new THREE.WebGLRenderTarget(1, 1),
    } as unknown as EffectComposer;
    const cv = crearCalidadVista(scene, new THREE.PerspectiveCamera(), group, composer);
    cv.ajustar(0); // en «normal» no hace nada
    expect(cv.gtao.gtaoMaterial.uniforms.radius.value).toBeCloseTo(0.25);
    cv.fijar("alta");
    const planos = [new THREE.Plane(new THREE.Vector3(1, 0, 0), 0)];
    (caja.material as THREE.Material).clippingPlanes = planos;
    cv.ajustar(1000);
    const diagonal = Math.hypot(1000, 600, 800);
    expect(cv.gtao.gtaoMaterial.uniforms.radius.value).toBeCloseTo(escalaOclusion(diagonal).radio);
    expect(cv.gtao.normalMaterial.clippingPlanes).toBe(planos);
    caja.scale.setScalar(2);
    cv.ajustar(1000 + INTERVALO_AJUSTE_MS / 2); // dentro del tope: no recalcula
    expect(cv.gtao.gtaoMaterial.uniforms.radius.value).toBeCloseTo(escalaOclusion(diagonal).radio);
    cv.ajustar(1000 + INTERVALO_AJUSTE_MS);
    expect(cv.gtao.gtaoMaterial.uniforms.radius.value).toBeCloseTo(escalaOclusion(diagonal * 2).radio);
  });
});
