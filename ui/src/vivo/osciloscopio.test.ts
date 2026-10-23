import { describe, expect, it } from "vitest";
import { capturar, Historia } from "./historia";
import {
  buscarDisparo, escalaDe, fuenteCaptura, fuenteHistoria, MAX_SENALES, PRE_DISPARO, quitarTrazo,
  sumarTrazo, ticksTiempo, ventana,
} from "./osciloscopio";
import { colorDato, PALETA_OSCURO } from "./paleta";

/* El osciloscopio de la sesión viva (plan V8.4 D6/D7): el anillo de la historia, la ventana
   deslizante, la escala por señal, los colores que siguen a la señal y el disparo por flanco. */

function llenar(h: Historia, desde: number, hasta: number, dt: number, f: (t: number) => Record<string, number>): void {
  for (let t = desde; t <= hasta + 1e-9; t += dt) {
    const v = f(t);
    h.empujar(t, Object.keys(v), Object.values(v));
  }
}

describe("historia (anillo)", () => {
  it("guarda en orden y descarta un tiempo que no avanza", () => {
    const h = new Historia(8);
    h.empujar(0, ["a"], [1]);
    h.empujar(0.1, ["a"], [2]);
    h.empujar(0.1, ["a"], [99]);
    expect(h.n).toBe(2);
    expect(h.valor("a", 1)).toBe(2);
  });

  it("al llenarse pisa lo más viejo y sigue ordenado", () => {
    const h = new Historia(4);
    llenar(h, 0, 0.9, 0.1, (t) => ({ a: t * 10 }));
    expect(h.n).toBe(4);
    expect(h.tPrimero()).toBeCloseTo(0.6);
    expect(h.tUltimo()).toBeCloseTo(0.9);
    expect([0, 1, 2, 3].map((k) => Math.round(h.valor("a", k)))).toEqual([6, 7, 8, 9]);
    expect(h.desde(0.75)).toBe(2);
    expect(h.desde(5)).toBe(4);
  });

  it("una señal que aparece después tiene NaN antes y el último valor se busca hacia atrás", () => {
    const h = new Historia(16);
    h.empujar(0, ["a"], [1]);
    h.empujar(0.1, ["a", "b"], [1, 5]);
    h.empujar(0.2, ["a"], [1]);
    expect(h.valor("b", 0)).toBeNaN();
    expect(h.valor("b", 2)).toBeNaN();
    expect(h.ultimoHasta("b", 2)).toBe(5);
    expect(h.valor("nadie", 0)).toBeNaN();
  });

  it("la captura copia la ventana y no cambia aunque el anillo siga", () => {
    const h = new Historia(8);
    llenar(h, 0, 0.5, 0.1, (t) => ({ a: t }));
    const c = capturar(h, ["a"], 0.2, 0.4);
    expect([...c.t].map((x) => Math.round(x * 10))).toEqual([2, 3, 4]);
    llenar(h, 0.6, 1.5, 0.1, (t) => ({ a: t }));
    const f = fuenteCaptura(c);
    expect(f.n).toBe(3);
    expect(f.valor("a", 0)).toBeCloseTo(0.2);
    expect(f.desde(0.35)).toBe(2);
  });
});

describe("señales y colores", () => {
  it("cada señal toma el primer color libre y lo conserva al quitar otras", () => {
    let tr = sumarTrazo([], "-M1.rpm")!;
    tr = sumarTrazo(tr, "-T2.f_Hz")!;
    tr = sumarTrazo(tr, "-M1.I_A")!;
    expect(tr.map((x) => x.color)).toEqual([0, 1, 2]);
    tr = quitarTrazo(tr, "-M1.rpm");
    expect(tr.find((x) => x.senal === "-T2.f_Hz")!.color).toBe(1); // no se repinta
    tr = sumarTrazo(tr, "-K1.Main.cuenta")!;
    expect(tr.find((x) => x.senal === "-K1.Main.cuenta")!.color).toBe(0);
    expect(sumarTrazo(tr, "-T2.f_Hz")).toHaveLength(3); // ya estaba
  });

  it("caben 8 (los colores de la paleta); la novena no inventa un color", () => {
    let tr = sumarTrazo([], "s0")!;
    for (let i = 1; i < MAX_SENALES; i++) tr = sumarTrazo(tr, `s${i}`)!;
    expect(tr).toHaveLength(PALETA_OSCURO.length);
    expect(sumarTrazo(tr, "s8")).toBeNull();
    expect(new Set(tr.map((x) => colorDato(x.color))).size).toBe(8);
  });
});

describe("ventana y escalas", () => {
  it("la ventana deslizante termina en la última muestra; con disparo, lo rodea", () => {
    expect(ventana(20, 37)).toEqual([17, 37]);
    expect(ventana(10, null)).toEqual([-10, 0]);
    const [t0, t1] = ventana(20, 50, 30);
    expect(t0).toBeCloseTo(30 - 20 * PRE_DISPARO);
    expect(t1 - t0).toBeCloseTo(20);
  });

  it("una escala por señal: su mínimo y máximo con margen; sí/no fija; constante con alto", () => {
    const h = new Historia(64);
    llenar(h, 0, 3, 0.1, (t) => ({ rpm: t * 600, on: t > 1 ? 1 : 0, cte: 230 }));
    const f = fuenteHistoria(h);
    const e = escalaDe(f, "rpm", 0, f.n, false);
    expect(e.lo).toBeLessThan(0);
    expect(e.hi).toBeGreaterThan(1800);
    expect(e.hi).toBeLessThan(1800 * 1.1);
    // sólo la ventana pedida cuenta
    const k0 = f.desde(2);
    expect(escalaDe(f, "rpm", k0, f.n, false).lo).toBeGreaterThan(1100);
    expect(escalaDe(f, "on", 0, f.n, true)).toEqual({ lo: -0.15, hi: 1.15 });
    const c = escalaDe(f, "cte", 0, f.n, false);
    expect(c.lo).toBeLessThan(230);
    expect(c.hi).toBeGreaterThan(230);
    expect(escalaDe(f, "nadie", 0, f.n, false)).toEqual({ lo: 0, hi: 1 });
  });

  it("ticks de tiempo redondos", () => {
    expect(ticksTiempo(0, 10)).toEqual([0, 2, 4, 6, 8, 10]);
    expect(ticksTiempo(17.3, 37.3)).toEqual([20, 25, 30, 35]);
    expect(ticksTiempo(5, 5)).toEqual([]);
  });
});

describe("disparo por flanco", () => {
  const h = new Historia(256);
  // corriente que sube de 4 a 13 A en t = 5 s y un relé que cae a 1 en t = 6,5 s
  llenar(h, 0, 10, 0.1, (t) => ({ I: t < 5 - 1e-9 ? 4 : 13, rele: t < 6.5 - 1e-9 ? 0 : 1 }));
  const f = fuenteHistoria(h);

  it("subida sobre un umbral, con el instante interpolado", () => {
    const t = buscarDisparo(f, "I", 8.5, "subida")!;
    expect(t).toBeGreaterThan(4.9);
    expect(t).toBeLessThanOrEqual(5);
    expect(t).toBeCloseTo(4.95, 2);
    expect(buscarDisparo(f, "rele", 0.5, "subida")).toBeCloseTo(6.45, 2);
  });

  it("bajada no dispara con una subida; nada antes de armar", () => {
    expect(buscarDisparo(f, "I", 8.5, "bajada")).toBeNull();
    expect(buscarDisparo(f, "I", 8.5, "subida", f.desde(6))).toBeNull();
  });

  it("bajada", () => {
    const g = new Historia(64);
    llenar(g, 0, 3, 0.1, (t) => ({ rpm: t < 2 - 1e-9 ? 1800 : 0 }));
    expect(buscarDisparo(fuenteHistoria(g), "rpm", 900, "bajada")).toBeCloseTo(1.95, 2);
  });
});
