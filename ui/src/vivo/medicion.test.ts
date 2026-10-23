import { beforeEach, describe, expect, it } from "vitest";
import {
  alternarMultimetro, alternarOsciloscopio, configurarDisparo, DISPARO_INICIAL, historia, rearmar,
  registrarMuestra, reiniciarHistoria, useInstrumentos,
} from "./medicion";

/* Los instrumentos de la sesión viva (plan V8.4 D7): el disparo avanza con cada fotograma
   (armado → disparado → congelado) y se re-arma; sumar y quitar señales. */

const st = () => useInstrumentos.getState();

function correr(desde: number, hasta: number, f: (t: number) => Record<string, number>): void {
  for (let k = Math.round(desde * 30); k <= Math.round(hasta * 30); k++) {
    const t = k / 30;
    const v = f(t);
    registrarMuestra(t, Object.keys(v), Object.values(v));
  }
}

const atasco = (t: number) => ({ "-M1.I_A": t < 5 ? 3.8 : 13, "-T2.rele_falla": t < 5.1 ? 0 : 1 });

beforeEach(() => {
  historia.limpiar();
  st().set({ trazos: [], multimetro: null, ancho: 10, disparo: DISPARO_INICIAL, aviso: null, plegado: false });
});

describe("sumar señales", () => {
  it("el osciloscopio alterna; el multímetro ancla una sola", () => {
    alternarOsciloscopio("-M1.rpm");
    alternarOsciloscopio("-T2.f_Hz");
    expect(st().trazos.map((x) => x.senal)).toEqual(["-M1.rpm", "-T2.f_Hz"]);
    alternarOsciloscopio("-M1.rpm");
    expect(st().trazos.map((x) => x.senal)).toEqual(["-T2.f_Hz"]);
    alternarMultimetro("-M1.I_A");
    alternarMultimetro("-T2.f_Hz");
    expect(st().multimetro).toBe("-T2.f_Hz");
    alternarMultimetro("-T2.f_Hz");
    expect(st().multimetro).toBeNull();
  });

  it("la novena señal no entra y lo dice", () => {
    for (let i = 0; i < 9; i++) alternarOsciloscopio(`s${i}`);
    expect(st().trazos).toHaveLength(8);
    expect(st().aviso).toMatch(/Caben 8/);
  });
});

describe("disparo en vivo", () => {
  it("armado → disparado en el flanco → congelado al llenar la ventana", () => {
    alternarOsciloscopio("-T2.rele_falla");
    alternarOsciloscopio("-M1.I_A");
    correr(0, 2, atasco);
    configurarDisparo({ senal: "-T2.rele_falla", flanco: "subida", umbral: 0.5 });
    expect(st().disparo.estado).toBe("armado");
    correr(2 + 1 / 30, 5, atasco);
    expect(st().disparo.estado).toBe("armado");
    correr(5 + 1 / 30, 6, atasco);
    expect(st().disparo.estado).toBe("disparado");
    const td = st().disparo.tDisparo!;
    expect(td).toBeGreaterThan(5.06);
    expect(td).toBeLessThan(5.14);
    // la ventana de 10 s deja 7,5 s después del disparo: a los 12,6 s se congela
    correr(6 + 1 / 30, 12.5, atasco);
    expect(st().disparo.estado).toBe("disparado");
    correr(12.5 + 1 / 30, 13, atasco);
    expect(st().disparo.estado).toBe("congelado");
    const c = st().disparo.captura!;
    expect(c.t[0]).toBeGreaterThanOrEqual(td - 2.5 - 1e-6);
    expect(c.t[c.t.length - 1]).toBeLessThanOrEqual(td + 7.5 + 1e-6);
    // todas las señales quedan en la captura (también una que se sume después)
    expect([...c.cols.keys()].sort()).toEqual(["-M1.I_A", "-T2.rele_falla"]);
    // congelado: lo que sigue llegando no la cambia
    correr(13 + 1 / 30, 15, atasco);
    expect(st().disparo.captura).toBe(c);
  });

  it("no dispara si la señal ya estaba arriba al armar; re-armar espera un flanco nuevo", () => {
    correr(0, 6, atasco);
    configurarDisparo({ senal: "-T2.rele_falla", umbral: 0.5 });
    correr(6 + 1 / 30, 8, atasco);
    expect(st().disparo.estado).toBe("armado");
    // baja y vuelve a subir
    correr(8 + 1 / 30, 9, () => ({ "-T2.rele_falla": 0 }));
    correr(9 + 1 / 30, 9.5, () => ({ "-T2.rele_falla": 1 }));
    expect(st().disparo.estado).toBe("disparado");
    expect(st().disparo.tDisparo).toBeGreaterThan(9);
    rearmar();
    expect(st().disparo.estado).toBe("armado");
    expect(st().disparo.tDisparo).toBeNull();
  });

  it("quitar la señal del disparo lo apaga; una sesión nueva re-arma desde cero", () => {
    alternarOsciloscopio("-T2.rele_falla");
    configurarDisparo({ senal: "-T2.rele_falla" });
    reiniciarHistoria();
    expect(st().disparo).toMatchObject({ estado: "armado", armadoEn: 0 });
    alternarOsciloscopio("-T2.rele_falla");
    expect(st().disparo.estado).toBe("apagado");
    expect(st().disparo.senal).toBeNull();
  });
});
