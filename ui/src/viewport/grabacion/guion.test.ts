import { describe, expect, it } from "vitest";
import { corrimiento } from "./acumulado";
import { avanceGiro, planGiro, posicionGiro, SEGUNDOS_GIRO, SEGUNDOS_MAX, tiempoMarcha } from "./guion";

/* El guion de F2 (la máquina girando y andando) y el corrimiento de las muestras del antialias
   acumulado (video-realista D3). */

describe("planGiro", () => {
  it("sin marcha, un giro de 8 s; con marcha, lo que dura ella, hasta un minuto", () => {
    expect(planGiro({ fps: 30 })).toMatchObject({ cuadros: SEGUNDOS_GIRO * 30, marcha: null });
    expect(planGiro({ fps: 30, marchaSegundos: 12.5 })).toMatchObject({ cuadros: 375, segundos: 12.5 });
    expect(planGiro({ fps: 30, marchaSegundos: 300 }).segundos).toBe(SEGUNDOS_MAX);
    expect(planGiro({ fps: 24, marchaSegundos: 12, segundos: 3 }).cuadros).toBe(72);
  });

  it("la marcha avanza 1/fps por cuadro y se queda en su final", () => {
    const plan = planGiro({ fps: 30, marchaSegundos: 2, segundos: 3 });
    expect(tiempoMarcha(plan, 0)).toBe(0);
    expect(tiempoMarcha(plan, 15)).toBe(0.5);
    expect(tiempoMarcha(plan, 89)).toBe(2);
    expect(tiempoMarcha(planGiro({ fps: 30 }), 40)).toBe(0); // sin marcha
  });
});

describe("el giro de la cámara", () => {
  const plan = planGiro({ fps: 30, segundos: 4, grados: 90 });

  it("arranca y frena suave, de 0 a 1", () => {
    expect(avanceGiro(0, plan.cuadros)).toBe(0);
    expect(avanceGiro(plan.cuadros - 1, plan.cuadros)).toBe(1);
    expect(avanceGiro(1, plan.cuadros)).toBeLessThan(1 / (plan.cuadros - 1)); // arranque lento
    expect(avanceGiro(0, 1)).toBe(0);
  });

  it("gira alrededor del eje Z por el objetivo sin cambiar altura ni distancia", () => {
    const objetivo: [number, number, number] = [100, 200, 50];
    const desde: [number, number, number] = [1100, 200, 700];
    expect(posicionGiro(objetivo, desde, plan, 0)).toEqual(desde);
    const fin = posicionGiro(objetivo, desde, plan, plan.cuadros - 1);
    expect(fin[0]).toBeCloseTo(100);
    expect(fin[1]).toBeCloseTo(1200); // 90° antihorario visto desde arriba
    expect(fin[2]).toBe(700);
    const medio = posicionGiro(objetivo, desde, plan, 50);
    expect(Math.hypot(medio[0] - 100, medio[1] - 200)).toBeCloseTo(1000);
  });
});

describe("corrimiento de las muestras", () => {
  it("queda dentro del píxel, sin repetirse ni caer en el centro", () => {
    const vistos = new Set<string>();
    for (let i = 0; i < 64; i++) {
      const [x, y] = corrimiento(i);
      expect(Math.abs(x)).toBeLessThan(0.5);
      expect(Math.abs(y)).toBeLessThan(0.5);
      vistos.add(`${x},${y}`);
    }
    expect(vistos.size).toBe(64);
    expect(corrimiento(0)).toEqual([0, 1 / 3 - 0.5]);
  });

  it("16 muestras cubren el píxel parejo (promedio cerca del centro)", () => {
    let sx = 0;
    let sy = 0;
    for (let i = 0; i < 16; i++) {
      const [x, y] = corrimiento(i);
      sx += x;
      sy += y;
    }
    expect(Math.abs(sx / 16)).toBeLessThan(0.05);
    expect(Math.abs(sy / 16)).toBeLessThan(0.05);
  });
});
