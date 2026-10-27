import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { arbolDeSenales, designacionDe, filtrarArbol } from "./arbolSenales";
import { juntaMotriz, rotulosDeJuntas } from "./mandos";
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
    expect(a.find((r) => r.clave === "-M1")).toEqual({ clave: "-M1", titulo: "-M1", senales: ["-M1.rpm", "-M1.I_A"] });
    expect(a.find((r) => r.clave === "-W3")).toEqual({ clave: "-W3", titulo: "-W3", senales: ["-W3.1.I_A"] });
    expect(a.find((r) => r.titulo === "Conductores")!.senales).toEqual(["c1620#1.I_A", "c1622.I_A"]);
    expect(a.find((r) => r.titulo === "Máquina")!.senales).toEqual(["c119.v_m_s", "caja_0.x_mm"]);
  });

  it("la designación es lo que va antes del primer punto", () => {
    expect(designacionDe("-K1.Main.cuenta")).toBe("-K1");
    expect(designacionDe("=F1-Q1.cerrado")).toBe("=F1-Q1");
    expect(designacionDe("c119.v_m_s")).toBeNull();
    expect(magnitud("-K1.%IX0.0")).toBe("%IX0.0");
  });

  it("cada aparato por lo que hace, con la designación detrás; un cable, por sus extremos (nombres-por-funcion F4)", () => {
    const conNombres = {
      dispositivos: DISPOSITIVOS.map((d) => ({ ...d, rotulo: d.designacion === "-M1" ? "Motor de la banda" : undefined })),
      ramas: [{ id: "-W3.1", tipo: "conductor", red: "potencia", nombre: "Cable Variador → Motor de la banda" },
        { id: "-W3:13-14", tipo: "contacto", red: "mando", nombre: "Contacto 13-14 · Otro" }],
    };
    const a = arbolDeSenales(conNombres, NOMBRES);
    expect(a.find((r) => r.clave === "-M1")).toMatchObject({ titulo: "Motor de la banda", designacion: "-M1" });
    expect(a.find((r) => r.clave === "-W3")).toMatchObject({ titulo: "Cable Variador → Motor de la banda", designacion: "-W3" });
    // se busca por el nombre y por la designación
    expect(filtrarArbol(a, "banda").map((r) => r.clave)).toEqual(["-M1", "-W3"]);
    expect(filtrarArbol(a, "-m1").map((r) => r.clave)).toEqual(["-M1"]);
  });

  it("sin tabla de tipos en la UI: lo que no nombra el servidor queda con su designación (D13)", () => {
    const fuente = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "arbolSenales.ts"), "utf8");
    for (const tipo of ["Relé de seguridad", "Electroválvula", "Seta de emergencia", "\"Cable\""]) expect(fuente).not.toContain(tipo);
  });

  it("buscar: el dispositivo entra entero; si no, sólo las señales que casan", () => {
    const a = arbolDeSenales({ dispositivos: DISPOSITIVOS.map((d) => d.designacion === "-T2" ? { ...d, rotulo: "Variador" } : d) },
      NOMBRES);
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

  it("cada junta por su pieza hija; el id sólo si dos se llamarían igual o falta el nombre (D15)", () => {
    const r = rotulosDeJuntas([
      { name: "j_eje_paletas", nombre: "Eje de paletas" }, { name: "c388_puerta", nombre: "Puerta del tablero" },
      { name: "j_rueda_1", nombre: "Rueda" }, { name: "j_rueda_2", nombre: "Rueda" }, { name: "j_vieja" },
    ]);
    expect([...r.values()]).toEqual(["Eje de paletas", "Puerta del tablero", "Rueda · j_rueda_1", "Rueda · j_rueda_2", "j_vieja"]);
  });
});

describe("el panel de operador en el árbol (plc-en-el-lazo D12)", () => {
  it("va bajo su nombre del servidor (el de su tipo, por A8) con la designación detrás", () => {
    const a = arbolDeSenales({ dispositivos: [{ designacion: "-P2", tipo: "hmi", ref: "HMI-7IN-24VDC", pantalla_px: [800, 480],
      rotulo: "Panel de operador", origen: "tipo" }] }, ["-P2.encendida"]);
    expect(a).toEqual([{ clave: "-P2", titulo: "Panel de operador", designacion: "-P2", senales: ["-P2.encendida"] }]);
  });
});
