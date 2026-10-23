import { describe, expect, it } from "vitest";
import { controlesBarra, rotuloFase, textoFactor } from "./barra";
import { formatear, lecturasDe, senalContador } from "./lecturas";
import { avanzarReloj, crearReloj, RETRASO_S } from "./reloj";

/* La barra de la sesión viva (fase, factor, botones), las lecturas del panel y las etiquetas, y
   el reloj del visor que sigue la última muestra (plan V8.4, F2). */

describe("barra de la sesión viva", () => {
  it("factor: ×1,00 normal; por debajo de ×0,995, en ámbar", () => {
    expect(textoFactor(0.998)).toEqual({ texto: "×1,00", lento: false });
    expect(textoFactor(0.8)).toEqual({ texto: "×0,80", lento: true });
    expect(textoFactor(NaN).texto).toBe("×—");
  });

  it("cada fase tiene su rótulo y sus botones", () => {
    expect(rotuloFase("corriendo")).toBe("En marcha");
    expect(rotuloFase("pausa")).toBe("En pausa");
    expect(rotuloFase("fin")).toBe("Terminó");
    expect(controlesBarra("corriendo")).toEqual({ pausar: true, reanudar: false, parar: true, reiniciar: false });
    expect(controlesBarra("pausa")).toEqual({ pausar: false, reanudar: true, parar: true, reiniciar: false });
    expect(controlesBarra("fin")).toEqual({ pausar: false, reanudar: false, parar: false, reiniciar: true });
    expect(controlesBarra("error").reiniciar).toBe(true);
    expect(controlesBarra("abriendo")).toEqual({ pausar: false, reanudar: false, parar: false, reiniciar: false });
  });
});

describe("lecturas", () => {
  const ini = {
    dispositivos: [
      { designacion: "-M1", tipo: "motor", ref: "NMRV-090", pieza: "c682" },
      { designacion: "-T2", tipo: "variador", ref: "VFD", pieza: "c1377" },
      { designacion: "-K1", tipo: "plc", ref: "PLC" },
      { designacion: "-H1", tipo: "piloto", ref: "PILOTO" },
    ],
  };
  const nombres = ["-M1.rpm", "-M1.I_A", "-T2.f_Hz", "-K1.%IX0.0", "-K1.Main.en_marcha", "-K1.Main.cuenta", "-H1.encendido"];

  it("motor (rpm, I), variador (Hz) y el contador del PLC; nada de otros tipos", () => {
    const l = lecturasDe(ini, nombres);
    expect(l.map((x) => x.designacion)).toEqual(["-M1", "-T2", "-K1"]);
    expect(l[0].lineas.map((x) => x.senal)).toEqual(["-M1.rpm", "-M1.I_A"]);
    expect(l[0].pieza).toBe("c682");
    expect(l[2].lineas[0].senal).toBe("-K1.Main.cuenta");
    expect(senalContador("-K1", ["-K1.Main.en_marcha"])).toBeNull();
    expect(lecturasDe(ini, ["-M1.par_Nm"])).toEqual([]); // sin sus señales, nada
  });

  it("formato con coma decimal y miles", () => {
    expect(formatear(1799.42, { unidad: "rpm", decimales: 0 })).toBe("1 799 rpm");
    expect(formatear(3.81, { unidad: "A", decimales: 1 })).toBe("3,8 A");
    expect(formatear(7, { unidad: "", decimales: 0 })).toBe("7");
    expect(formatear(undefined, { unidad: "Hz", decimales: 1 })).toBe("—");
    expect(formatear(-0.01, { unidad: "Hz", decimales: 1 })).toBe("0,0 Hz");
  });
});

describe("reloj del visor", () => {
  it("arranca un poco antes de la última muestra y avanza con la pared sin pasarla", () => {
    const r = crearReloj();
    expect(avanzarReloj(r, 0, null, 1)).toBeNull();
    expect(avanzarReloj(r, 0, 1, 1)).toBeCloseTo(1 - RETRASO_S, 6);
    // 30 fotogramas por segundo a tiempo real, 60 cuadros por segundo: sigue suave y detrás
    let tUlt = 1;
    let previo = 1 - RETRASO_S;
    for (let k = 1; k <= 120; k++) {
      if (k % 2 === 0) tUlt += 1 / 30;
      const t = avanzarReloj(r, k * (1000 / 60), tUlt, 1)!;
      expect(t).toBeGreaterThanOrEqual(previo); // nunca retrocede
      expect(t).toBeLessThanOrEqual(tUlt);
      previo = t;
    }
    expect(previo).toBeGreaterThan(tUlt - 0.15);
  });

  it("en pausa (no llegan muestras) se queda en la última; un hueco grande salta", () => {
    const r = crearReloj();
    avanzarReloj(r, 0, 5, 1);
    let t = 0;
    for (let k = 1; k <= 300; k++) t = avanzarReloj(r, k * 16, 5, 1)!;
    expect(t).toBeLessThanOrEqual(5);
    expect(t).toBeGreaterThan(5 - RETRASO_S - 1e-9);
    expect(avanzarReloj(r, 5000, 12, 1)).toBeCloseTo(12 - RETRASO_S, 6);
  });
});
