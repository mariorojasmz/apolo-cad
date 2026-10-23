import { describe, expect, it } from "vitest";
import { arbolDeSenales, designacionDe, filtrarArbol } from "./arbolSenales";
import { juntaMotriz } from "./mandos";
import { leerValor, magnitud, medidaDe } from "./unidades";

/* El árbol de señales (plan V8.4 D7) y la lectura de cada señal por su nombre. */

const DISPOSITIVOS = [
  { designacion: "-Q1", tipo: "seccionador", ref: "SEC" },
  { designacion: "-T2", tipo: "variador", ref: "VFD" },
  { designacion: "-K1", tipo: "plc", ref: "PLC" },
  { designacion: "-H1", tipo: "piloto", ref: "P" }, // sin señales: no sale
  { designacion: "-M1", tipo: "motor", ref: "NMRV", pieza: "c682" },
];

const NOMBRES = [
  "-Q1.cerrado", "-T2.f_Hz", "-T2.rele_falla", "-K1.%IX0.0", "-K1.pb_marcha", "-K1.Main.cuenta",
  "-M1.rpm", "-M1.I_A", "c1620#1.I_A", "c1622.I_A", "-W3.1.I_A", "c119.v_m_s", "caja_0.x_mm", undefined,
  "-M1.rpm", // repetida
];

describe("árbol de señales", () => {
  it("dispositivo → señales en el orden del tablero; cables, conductores y máquina aparte", () => {
    const a = arbolDeSenales({ dispositivos: DISPOSITIVOS }, NOMBRES);
    expect(a.map((r) => r.titulo)).toEqual(["-Q1", "-T2", "-K1", "-M1", "-W3", "Conductores", "Máquina"]);
    expect(a.find((r) => r.clave === "-K1")!.senales).toEqual(["-K1.%IX0.0", "-K1.pb_marcha", "-K1.Main.cuenta"]);
    expect(a.find((r) => r.clave === "-M1")).toMatchObject({ rotulo: "Motor", senales: ["-M1.rpm", "-M1.I_A"] });
    expect(a.find((r) => r.clave === "-W3")).toMatchObject({ rotulo: "Cable", senales: ["-W3.1.I_A"] });
    expect(a.find((r) => r.titulo === "Conductores")!.senales).toEqual(["c1620#1.I_A", "c1622.I_A"]);
    expect(a.find((r) => r.titulo === "Máquina")!.senales).toEqual(["c119.v_m_s", "caja_0.x_mm"]);
  });

  it("la designación es lo que va antes del primer punto", () => {
    expect(designacionDe("-K1.Main.cuenta")).toBe("-K1");
    expect(designacionDe("=F1-Q1.cerrado")).toBe("=F1-Q1");
    expect(designacionDe("c119.v_m_s")).toBeNull();
    expect(magnitud("-K1.%IX0.0")).toBe("%IX0.0");
  });

  it("buscar: el dispositivo entra entero; si no, sólo las señales que casan", () => {
    const a = arbolDeSenales({ dispositivos: DISPOSITIVOS }, NOMBRES);
    expect(filtrarArbol(a, "variador").map((r) => r.clave)).toEqual(["-T2"]);
    const rpm = filtrarArbol(a, "RPM");
    expect(rpm.map((r) => r.clave)).toEqual(["-M1"]);
    expect(rpm[0].senales).toEqual(["-M1.rpm"]);
    expect(filtrarArbol(a, "  ")).toHaveLength(a.length);
    expect(filtrarArbol(a, "nada-que-ver")).toEqual([]);
  });
});

describe("leer una señal por su nombre", () => {
  it("unidades por sufijo y sí/no por nombre", () => {
    expect(leerValor(1799.4, medidaDe("-M1.rpm"))).toBe("1 799 rpm");
    expect(leerValor(3.814, medidaDe("-M1.I_A"))).toBe("3,81 A");
    expect(leerValor(60, medidaDe("-T2.f_Hz"))).toBe("60,0 Hz");
    expect(leerValor(24.08, medidaDe("-M1.par_Nm"))).toBe("24,08 N·m");
    expect(leerValor(1.2, medidaDe("c119.v_m_s"))).toBe("1,20 m/s");
    expect(leerValor(12.5, medidaDe("-T2.termico_pct"))).toBe("12,5 %");
    expect(leerValor(1, medidaDe("-Q1.cerrado"))).toBe("Sí");
    expect(leerValor(0, medidaDe("-T2.rele_falla"))).toBe("No");
    expect(leerValor(1, medidaDe("-K1.%QX0.0"))).toBe("Sí");
    expect(leerValor(undefined, medidaDe("-M1.rpm"))).toBe("—");
    expect(leerValor(-0.001, medidaDe("-M1.rpm"))).toBe("0 rpm");
  });

  it("el tipo del PLC manda: BOOL es sí/no, INT entero", () => {
    expect(medidaDe("-K1.Main.en_marcha", "BOOL").booleana).toBe(true);
    expect(leerValor(7, medidaDe("-K1.Main.cuenta", "INT"))).toBe("7");
    expect(medidaDe("-K1.Main.en_marcha").booleana).toBe(false); // sin el tipo, no se adivina
  });
});

describe("atasco provocado", () => {
  it("frena la junta de la banda; sin banda, la primera junta", () => {
    expect(juntaMotriz({ bandas: [{ junta: "j_eje_motriz" }], juntas: [{ name: "j_tensor" }, { name: "j_eje_motriz" }] })).toBe("j_eje_motriz");
    expect(juntaMotriz({ bandas: [], juntas: [{ name: "j_tambor" }] })).toBe("j_tambor");
    expect(juntaMotriz({ bandas: [], juntas: [] })).toBeNull();
  });
});
