import { describe, expect, it } from "vitest";
import type { PlanGuion, TramoPlan } from "../planGuion";
import {
  aleatorioConSemilla, estimarSegundos, NIVEL_POR_DEFECTO, nivelDeTexto, nombreFoto, opcionesTrazado,
  pedidoDeUrl, planTrazado, semillaDeCuadro, seTraza, tamanoFoto, TRAZADO_FOTO, TRAZADO_VIDEO,
} from "./nivel";

/* Los niveles del video y la foto realista (video-realista D6, F4): el máximo existe pero no es
   el de por defecto; opciones acotadas; la semilla; la URL del CLI; y qué cuadros del guion pasan
   por el trazador. */

describe("niveles y opciones del trazado", () => {
  it("el nivel por defecto es el rápido; el máximo hay que pedirlo", () => {
    expect(NIVEL_POR_DEFECTO).toBe("rapido");
    expect(nivelDeTexto("máximo")).toBe("maximo");
    expect(nivelDeTexto(" RAPIDO ")).toBe("rapido");
    expect(nivelDeTexto("ultra")).toBeNull();
    expect(nivelDeTexto(null)).toBeNull();
  });

  it("la foto lleva más muestras que un cuadro del video y las dos el denoiser", () => {
    expect(TRAZADO_FOTO.muestras).toBeGreaterThan(TRAZADO_VIDEO.muestras);
    expect(TRAZADO_VIDEO.denoise).not.toBeNull();
    expect(TRAZADO_FOTO.semilla).toBe(TRAZADO_VIDEO.semilla);
  });

  it("acota lo pedido a valores que no cuelgan la GPU y conserva lo que no se pidió", () => {
    const o = opcionesTrazado(TRAZADO_VIDEO, { muestras: 1e9, rebotes: 0, teselas: 2.6, semilla: -7.4 });
    expect(o).toMatchObject({ muestras: 8192, rebotes: 1, teselas: 3, semilla: 7 });
    expect(o.denoise).toEqual(TRAZADO_VIDEO.denoise);
    expect(opcionesTrazado(TRAZADO_FOTO, { muestras: undefined })).toEqual(TRAZADO_FOTO);
    expect(opcionesTrazado(TRAZADO_VIDEO, { muestras: Number.NaN }).muestras).toBe(TRAZADO_VIDEO.muestras);
    expect(opcionesTrazado(TRAZADO_VIDEO, { denoise: null }).denoise).toBeNull();
    expect(opcionesTrazado(TRAZADO_VIDEO, { denoise: { sigma: 0, kSigma: 1, umbral: 1 } }).denoise).toBeNull();
  });

  it("en el video la semilla es la misma en todos los cuadros, salvo que se pida una por cuadro", () => {
    expect(semillaDeCuadro(TRAZADO_VIDEO, 0)).toBe(semillaDeCuadro(TRAZADO_VIDEO, 1799));
    const porCuadro = opcionesTrazado(TRAZADO_VIDEO, { semillaPorCuadro: true, semilla: 10 });
    expect([0, 1, 2].map((n) => semillaDeCuadro(porCuadro, n))).toEqual([10, 11, 12]);
  });

  it("el aleatorio con semilla repite su serie y otra semilla da otra", () => {
    const serie = (s: number) => { const r = aleatorioConSemilla(s); return [r(), r(), r(), r()]; };
    expect(serie(20261021)).toEqual(serie(20261021));
    expect(serie(1)).not.toEqual(serie(2));
    expect(serie(5).every((x) => x >= 0 && x < 1)).toBe(true);
  });
});

describe("la URL del CLI y la foto", () => {
  it("`--nivel maximo` llega por la URL; sin nivel, nada", () => {
    expect(pedidoDeUrl("?grabar=abcdef123456")).toBeNull();
    expect(pedidoDeUrl("?grabar=abcdef123456&nivel=maximo")).toEqual({ nivel: "maximo" });
    expect(pedidoDeUrl("?nivel=maximo&muestras=64&semilla=3")).toEqual({ nivel: "maximo", muestras: 64, semilla: 3 });
    expect(pedidoDeUrl("?nivel=maximo&muestras=-4&semilla=x")).toEqual({ nivel: "maximo" });
  });

  it("la foto tiene la proporción de la vista, con el lado mayor fijo y pares", () => {
    expect(tamanoFoto(1600, 858)).toEqual({ ancho: 1920, alto: 1030 });
    expect(tamanoFoto(500, 1000, 1000)).toEqual({ ancho: 500, alto: 1000 });
    expect(tamanoFoto(0, 0)).toEqual({ ancho: 1920, alto: 1920 });
  });

  it("el archivo lleva el proyecto sin acentos y la hora", () => {
    const f = new Date(2026, 9, 21, 7, 5, 9);
    expect(nombreFoto("Faja paquetería 4 m (copia)", f)).toBe("foto-realista-faja-paqueteria-4-m-copia-20261021-070509.png");
    expect(nombreFoto(null, f)).toBe("foto-realista-20261021-070509.png");
  });
});

describe("el plan de cuadros del grabador con el nivel máximo", () => {
  const tramo = (parte: TramoPlan["parte"], inicio: number, fin: number): TramoPlan =>
    ({ parte, inicio, fin, etapa: parte === "etapa" ? 0 : null, cruza: false });
  const plan = {
    cuadros: 300,
    tramos: [tramo("portada", 0, 60), tramo("etapa", 60, 150), tramo("marcha", 150, 210),
      tramo("cifras", 210, 240), tramo("orbita", 240, 270), tramo("cierre", 270, 300)],
  } as PlanGuion;

  it("sólo las partes 3D pasan por el trazador; las tarjetas no", () => {
    expect(planTrazado(plan)).toEqual({ cuadros: 300, trazados: 180, tarjetas: 120 });
    expect([0, 59, 60, 149, 150, 209, 210, 240, 269, 270].map((n) => seTraza(plan, n)))
      .toEqual([false, false, true, true, true, true, false, true, true, false]);
  });

  it("estima el tiempo con los segundos por cuadro medidos", () => {
    expect(estimarSegundos(planTrazado(plan), 40, 0.05)).toBeCloseTo(180 * 40 + 120 * 0.05);
  });
});
