import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { describe, expect, it } from "vitest";
import { dibujarConsigna, tocarConsigna } from "../diseno/muestrario/extensionPrueba";
import type { MensajeExtension, VivoPantalla } from "../extensiones/tipos";
import { alMundo, caraFrontal, matrizDeCara, pantallasDeLaSesion, rectanguloPantalla, temaDe, uvAPx, type Tripla } from "./pantallas";
import { problemaDeCierre, problemaDeMensaje, textoFin, type DispositivoVivo, type InicioVivo } from "./protocolo";
import { urlSesion } from "./sesion";

/* Las pantallas 3D de las extensiones (plan plc-en-el-lazo, D13 b): la cara frontal de la pieza
   (también girada), el rectángulo de la pantalla, uv → px, qué dispositivo lleva qué pantalla, y
   la API viva: el mensaje de una extensión y el PLC externo al abrir la sesión (D13 c, D6). */

/** El panel de 7″ como lo arma `panel_puerta`: marco 200,3 × 7,4 × 146,3 en +Y, cuerpo detrás. */
function panel(): THREE.BufferGeometry {
  const marco = new THREE.BoxGeometry(200.3, 7.4, 146.3).translate(0, 35 / 2 - 7.4 / 2, 0);
  const cuerpo = new THREE.BoxGeometry(189.6, 27.8, 135.6).translate(0, -35 / 2 + 27.8 / 2, 0);
  return mergeGeometries([marco, cuerpo])!;
}

const cara = (g: THREE.BufferGeometry, m: THREE.Matrix4 | null = null) =>
  caraFrontal(g.getAttribute("position").array, g.index?.array ?? null, m ? m.elements : null)!;

const cerca = (a: readonly number[], b: readonly number[], tol = 1e-6) =>
  a.forEach((x, i) => expect(x, `componente ${i}: ${a} vs ${b}`).toBeCloseTo(b[i], Math.round(-Math.log10(tol))));

/** El tablero girado `grados` sobre Z, con el panel en la puerta (su +Y mira a −Y del tablero). */
function enLaPuerta(grados: number): THREE.Matrix4 {
  const tablero = new THREE.Matrix4().makeRotationZ(THREE.MathUtils.degToRad(grados));
  const local = new THREE.Matrix4().makeRotationZ(Math.PI).setPosition(40, -91.9, 430);
  return tablero.multiply(local);
}

describe("la cara frontal de una pieza", () => {
  it("el panel suelto: gana el marco (+Y), con u a la derecha y v arriba vistos de frente", () => {
    const c = cara(panel());
    cerca(c.normal, [0, 1, 0]);
    cerca(c.centro, [0, 17.5, 0], 1e-4);
    expect(c.ancho).toBeCloseTo(200.3, 4);
    expect(c.alto).toBeCloseTo(146.3, 4);
    cerca(c.v, [0, 0, 1]);
    cerca(c.u, [-1, 0, 0]); // mirando desde +Y hacia −Y, la derecha es −X
    const n = [c.u[1] * c.v[2] - c.u[2] * c.v[1], c.u[2] * c.v[0] - c.u[0] * c.v[2], c.u[0] * c.v[1] - c.u[1] * c.v[0]];
    cerca(n, c.normal);
  });

  it("en la puerta de un tablero girado (instancia con matriz): la normal mira afuera de la puerta", () => {
    for (const grados of [0, 25, 90, 180, -137]) {
      const m = enLaPuerta(grados);
      const c = cara(panel(), m);
      const g = THREE.MathUtils.degToRad(grados);
      const afuera: Tripla = [Math.sin(g), -Math.cos(g), 0]; // −Y del tablero, en el mundo
      cerca(alMundo(m.elements, c.normal), afuera);
      cerca(alMundo(m.elements, c.v), [0, 0, 1]); // la pantalla no queda de costado ni cabeza abajo
      // vista desde afuera, u va hacia +X del tablero (la derecha de quien mira la puerta)
      cerca(alMundo(m.elements, c.u), [Math.cos(g), Math.sin(g), 0]);
    }
  });

  it("la geometría ya en el mundo (sin matriz) y girada fuera de los ejes da la misma cara", () => {
    const m = enLaPuerta(25).multiply(new THREE.Matrix4().makeRotationY(THREE.MathUtils.degToRad(12)));
    const c = cara(panel().applyMatrix4(m));
    const conMatriz = cara(panel(), m);
    cerca(c.normal, alMundo(m.elements, conMatriz.normal), 1e-5);
    cerca(c.v, alMundo(m.elements, conMatriz.v), 1e-5);
    expect(c.ancho).toBeCloseTo(200.3, 3);
    expect(c.alto).toBeCloseTo(146.3, 3);
    cerca(c.centro, new THREE.Vector3(...conMatriz.centro).applyMatrix4(m).toArray(), 1e-3);
  });

  it("una placa lisa (frente = dorso): gana la que mira hacia −Y del mundo, la vista «frente»", () => {
    const placa = new THREE.BoxGeometry(300, 4, 200);
    cerca(cara(placa).normal, [0, -1, 0]);
    const girada = new THREE.Matrix4().makeRotationZ(Math.PI);
    cerca(alMundo(girada.elements, cara(placa, girada).normal), [0, -1, 0]);
  });

  it("una cara que mira arriba se orienta hacia +Y del mundo; sin triángulos, null", () => {
    const tapa = new THREE.BoxGeometry(300, 200, 20).translate(0, 0, 10);
    const conMarco = mergeGeometries([tapa, new THREE.BoxGeometry(250, 150, 30).translate(0, 0, -15)])!;
    const c = cara(conMarco);
    cerca(c.normal, [0, 0, 1]);
    cerca(c.v, [0, 1, 0]);
    expect(caraFrontal([], null)).toBeNull();
  });

  it("la matriz del plano lleva x → u, y → v, z → normal y lo separa de la cara", () => {
    const c = cara(panel());
    const m = new THREE.Matrix4().fromArray(matrizDeCara(c, 0.4));
    cerca(new THREE.Vector3(1, 0, 0).transformDirection(m).toArray(), c.u);
    cerca(new THREE.Vector3(0, 0, 1).transformDirection(m).toArray(), c.normal);
    cerca(new THREE.Vector3().applyMatrix4(m).toArray(), [0, 17.9, 0], 1e-4);
  });
});

describe("el rectángulo de la pantalla y los toques", () => {
  it("con pantalla_px, su proporción dentro del marco; sin ella, la cara a 4 px/mm", () => {
    const r = rectanguloPantalla(200.3, 146.3, [800, 480]);
    expect(r.px).toEqual([800, 480]);
    expect(r.ancho / r.alto).toBeCloseTo(800 / 480, 6);
    expect(r.ancho).toBeLessThanOrEqual(200.3 * 0.82 + 1e-9);
    expect(r.alto).toBeLessThanOrEqual(146.3 * 0.82 + 1e-9);
    const sin = rectanguloPantalla(100, 50, undefined, 1);
    expect(sin).toEqual({ ancho: 100, alto: 50, px: [400, 200] });
    expect(rectanguloPantalla(1000, 5, null, 1).px).toEqual([2048, 64]);
  });

  it("uv → px: (0, 1) es el píxel de arriba a la izquierda y nada se sale del canvas", () => {
    const px: [number, number] = [800, 480];
    expect(uvAPx({ x: 0, y: 1 }, px)).toEqual({ x: 0, y: 0 });
    expect(uvAPx({ x: 1, y: 0 }, px)).toEqual({ x: 799, y: 479 });
    expect(uvAPx({ x: 0.5, y: 0.5 }, px)).toEqual({ x: 400, y: 240 });
    expect(uvAPx({ x: 0.25, y: 0.75 }, px)).toEqual({ x: 200, y: 120 });
    expect(uvAPx({ x: -0.1, y: 1.2 }, px)).toEqual({ x: 0, y: 0 });
  });

  it("cada dispositivo con pieza y una pantalla para su tipo; sin pieza en el 3D, ninguno", () => {
    const pantalla = { id: "prueba.hmi" as const, tipo: "hmi", dibujar: () => {} };
    const ds: DispositivoVivo[] = [
      { designacion: "-P1", tipo: "hmi", ref: "HMI", pieza: "p1" },
      { designacion: "-P2", tipo: "hmi", ref: "HMI" }, // sin pieza ligada
      { designacion: "-P3", tipo: "hmi", ref: "HMI", pieza: "borrada" },
      { designacion: "-K1", tipo: "plc", ref: "PLC", pieza: "k1" },
    ];
    const out = pantallasDeLaSesion(ds, [pantalla], (id) => id === "p1" || id === "k1");
    expect(out.map((x) => x.dispositivo.designacion)).toEqual(["-P1"]);
    expect(out[0].pantalla).toBe(pantalla);
  });

  it("el tema sale de los tokens; uno que falta cae al del tema oscuro", () => {
    const tokens: Record<string, string> = { "--panel": " #222 ", "--accent": "#5b8cff" };
    const t = temaDe((n) => tokens[n] ?? "", "Inter, sans-serif");
    expect(t.panel).toBe("#222");
    expect(t.acento).toBe("#5b8cff");
    expect(t.fondo).toBe("#121419");
    expect(t.fuente).toBe("Inter, sans-serif");
  });
});

describe("la pantalla de prueba del muestrario", () => {
  const inicio = { dispositivos: [{ designacion: "-K1", tipo: "plc", ref: "PLC" }] } as unknown as InicioVivo;
  const vivo = (enviados: MensajeExtension[], consigna?: number): VivoPantalla => ({
    dispositivo: { designacion: "-P1", tipo: "hmi", ref: "HMI-7IN-24VDC", pieza: "p1", pantalla_px: [800, 480] },
    inicio, ancho: 800, alto: 480, t: 1.5, movimientoReducido: false,
    valor: (s) => (s === "-K1.Main.consigna" ? consigna : undefined), texto: () => undefined,
    enviar: (m) => { enviados.push(m); return true; },
    tema: temaDe(() => ""),
  });

  it("tocar «+10» o «−10» manda un `escribir` al PLC; tocar arriba, nada", () => {
    const enviados: MensajeExtension[] = [];
    tocarConsigna(600, 400, vivo(enviados, 50));
    tocarConsigna(100, 400, vivo(enviados, 0));
    tocarConsigna(600, 50, vivo(enviados, 50));
    expect(enviados).toEqual([
      { accion: "escribir", dispositivo: "-K1", variable: "Main.consigna", valor: 60 },
      { accion: "escribir", dispositivo: "-K1", variable: "Main.consigna", valor: 0 },
    ]);
    for (const m of enviados) expect(problemaDeMensaje(m)).toBeNull();
  });

  it("pinta con los colores del tema", () => {
    const llamadas: string[] = [];
    const ctx = new Proxy({}, {
      get: (_o, k) => (k === "fillText" ? (t: string) => llamadas.push(t) : () => {}),
      set: (_o, k, v) => { if (k === "fillStyle") llamadas.push(`color ${v}`); return true; },
    }) as unknown as CanvasRenderingContext2D;
    dibujarConsigna(ctx, vivo([], 50));
    expect(llamadas).toContain("50 %");
    expect(llamadas).toContain("+10");
    expect(llamadas.filter((l) => l.startsWith("color ")).every((l) => ["#121419", "#1e222b", "#dfe4ec", "#8b93a3", "#5b8cff"]
      .includes(l.slice(6)))).toBe(true);
  });
});

describe("la API viva: mensajes de una extensión y el PLC externo", () => {
  it("una acción o un evento valen; un control, un id propio o los dos juntos, no", () => {
    expect(problemaDeMensaje({ accion: "escribir", dispositivo: "-K1", variable: "Main.x", valor: 1 })).toBeNull();
    expect(problemaDeMensaje({ evento: { tipo: "atasco" } })).toBeNull();
    expect(problemaDeMensaje({ control: "parar" })).toMatch(/de la persona/);
    expect(problemaDeMensaje({ accion: "pulsar", id: "a1" })).toMatch(/id/);
    expect(problemaDeMensaje({ accion: "pulsar", evento: {} })).toMatch(/uno solo/);
    expect(problemaDeMensaje({})).toMatch(/uno solo/);
    expect(problemaDeMensaje([1])).toMatch(/objeto/);
    expect(problemaDeMensaje({ accion: "escribir", valor: "x".repeat(5000) })).toMatch(/4096/);
  });

  it("abrir con un PLC externo lo pide en la query `plc_externo`; sin él, la URL de siempre", () => {
    const lugar = { protocol: "http:", host: "127.0.0.1:5199" };
    const sin = urlSesion("d1", "marcha", false, null, lugar);
    expect(sin).toBe("ws://127.0.0.1:5199/api/cosim/vivo?documento=d1&escenario=marcha");
    expect(urlSesion("d1", "marcha", false, {}, lugar)).toBe(sin);
    const externo = { "-K1": { conector: "prueba.tcp", config: { puerto: 5020 } } };
    const url = new URL(urlSesion("d1", "marcha", true, externo, { protocol: "https:", host: "apolo" }));
    expect(url.protocol).toBe("wss:");
    expect(url.searchParams.get("reemplazar")).toBe("1");
    expect(JSON.parse(url.searchParams.get("plc_externo")!)).toEqual(externo);
  });

  it("el PLC externo que no conecta (4502) y el lazo cortado tienen su texto", () => {
    expect(problemaDeCierre(4502, "timeout").texto).toMatch(/PLC externo/);
    expect(textoFin("lazo")).toMatch(/lazo con el PLC externo/);
  });
});
