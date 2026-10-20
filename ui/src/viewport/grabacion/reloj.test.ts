import { describe, expect, it } from "vitest";
import { cuadrosPara, GrabacionCancelada, msDeCuadro, recorrerCuadros } from "./reloj";

/* Reloj virtual de la grabación (video-realista D3): N cuadros, ni uno saltado ni duplicado,
   dibujados en orden aunque cada uno tarde distinto y aunque las subidas terminen desordenadas. */

const espera = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const blob = (n: number) => new Blob([String(n)], { type: "image/jpeg" });

/** Un recorrido con tiempos de dibujo y de subida pseudoaleatorios (semilla fija). */
function simulado(cuadros: number, fps = 30, enVuelo = 4) {
  let semilla = 7;
  const azar = () => ((semilla = (semilla * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
  const dibujos: { n: number; ms: number }[] = [];
  const subidas: number[] = [];
  let enCurso = 0;
  let maxEnCurso = 0;
  let dibujando = false;
  const op = {
    cuadros, fps, enVuelo,
    dibujar: async (n: number, ms: number) => {
      expect(dibujando, "dos cuadros dibujándose a la vez").toBe(false);
      dibujando = true;
      await espera(azar() * 3); // un cuadro lento no cambia su reloj
      dibujos.push({ n, ms });
      dibujando = false;
      enCurso++;
      maxEnCurso = Math.max(maxEnCurso, enCurso);
      return { foto: espera(azar() * 4).then(() => blob(n)) };
    },
    subir: async (n: number, foto: Blob) => {
      expect(await foto.text()).toBe(String(n));
      await espera(azar() * 4);
      subidas.push(n);
      enCurso--;
    },
  };
  return { op, dibujos, subidas, maxEnCurso: () => maxEnCurso };
}

describe("msDeCuadro y cuadrosPara", () => {
  it("el cuadro n vale t0 + n/fps, exacto también lejos del inicio", () => {
    expect(msDeCuadro(0, 30)).toBe(0);
    expect(msDeCuadro(3, 30)).toBe(100);
    expect(msDeCuadro(1799, 30, 500)).toBeCloseTo(500 + 59966.6667, 3);
    expect(msDeCuadro(1800, 30)).toBe(60000); // sin error acumulado
  });

  it("cuadros de un video", () => {
    expect(cuadrosPara(60, 30)).toBe(1800);
    expect(cuadrosPara(10.03, 30)).toBe(301);
    expect(cuadrosPara(0, 30)).toBe(1);
  });
});

describe("recorrerCuadros", () => {
  it("dibuja los N cuadros en orden, cada uno una vez, con su reloj", async () => {
    const s = simulado(40);
    await recorrerCuadros(s.op);
    expect(s.dibujos.map((d) => d.n)).toEqual([...Array(40).keys()]);
    s.dibujos.forEach((d) => expect(d.ms).toBe(msDeCuadro(d.n, 30)));
  });

  it("sube cada cuadro exactamente una vez aunque terminen desordenados", async () => {
    const s = simulado(40);
    await recorrerCuadros(s.op);
    expect(s.subidas).toHaveLength(40);
    expect([...s.subidas].sort((a, b) => a - b)).toEqual([...Array(40).keys()]);
    expect(s.subidas).not.toEqual([...Array(40).keys()]); // de verdad llegaron desordenadas
  });

  it("no deja más de `enVuelo` cuadros codificándose o subiendo a la vez", async () => {
    const s = simulado(30, 30, 3);
    await recorrerCuadros(s.op);
    expect(s.maxEnCurso()).toBeLessThanOrEqual(3);
    const uno = simulado(10, 30, 1);
    await recorrerCuadros(uno.op);
    expect(uno.maxEnCurso()).toBe(1);
    expect(uno.subidas).toEqual([...Array(10).keys()]); // de a uno: en orden
  });

  it("al primer error deja de dibujar, espera a los que estaban en vuelo y lo relanza", async () => {
    const s = simulado(50);
    const subir = s.op.subir;
    s.op.subir = async (n, foto) => {
      if (n === 7) throw new Error("se cayó la API");
      return subir(n, foto);
    };
    await expect(recorrerCuadros(s.op)).rejects.toThrow("se cayó la API");
    const ultimo = Math.max(...s.dibujos.map((d) => d.n));
    expect(ultimo).toBeLessThan(7 + 10); // pocos más: los que alcanzaron a dibujarse en vuelo
    expect(s.subidas).not.toContain(7);
  });

  it("un error al dibujar corta igual", async () => {
    const s = simulado(10);
    const dibujar = s.op.dibujar;
    s.op.dibujar = async (n, ms) => {
      if (n === 3) throw new Error("se perdió el contexto WebGL");
      return dibujar(n, ms);
    };
    await expect(recorrerCuadros(s.op)).rejects.toThrow("contexto WebGL");
    expect(s.dibujos.map((d) => d.n)).toEqual([0, 1, 2]);
    expect([...s.subidas].sort()).toEqual([0, 1, 2]); // los ya dibujados terminaron de subir
  });

  it("se puede cancelar entre cuadros", async () => {
    const s = simulado(20);
    let n = 0;
    await expect(recorrerCuadros({ ...s.op, cancelado: () => n++ >= 5 }))
      .rejects.toBeInstanceOf(GrabacionCancelada);
    expect(s.dibujos).toHaveLength(5);
  });

  it("informa el avance hasta el total", async () => {
    const s = simulado(12);
    const avances: number[] = [];
    await recorrerCuadros({ ...s.op, progreso: (a) => avances.push(a.subidos) });
    expect(Math.max(...avances)).toBe(12);
  });
});
