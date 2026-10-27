import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { aparatoDePieza, aparatosDeNeumatica } from "../visor/aparatoDePieza";
import { APARATOS_MEZCLADORA, PANEL_CON_FALLAS } from "./muestrario/datosTablero";
import { INICIO_DEMO } from "./muestrario/datosVivo";
import { designacionSecundaria, nombreDeJunta, nombreEnLinea, nombrePrincipal, partesSecundarias } from "./nombres";

/* El nombre de un aparato en todas las superficies (plan nombres-por-funcion F4): el rótulo del
   servidor primero, la designación detrás y chica; sin rótulo, la designación, nunca una tabla de
   tipos de la UI. */

const AQUI = dirname(fileURLToPath(import.meta.url));
const fuente = (ruta: string) => readFileSync(join(AQUI, "..", ruta), "utf8");

describe("rótulo primero, designación detrás", () => {
  it("con rótulo, el rótulo manda y la designación y el detalle van detrás", () => {
    const k3 = { designacion: "-K3", rotulo: "Seguridad del recipiente" };
    expect(nombrePrincipal(k3)).toBe("Seguridad del recipiente");
    expect(designacionSecundaria(k3)).toBe("-K3");
    expect(partesSecundarias(k3, "Relé de seguridad 2 canales")).toEqual(["-K3", "Relé de seguridad 2 canales"]);
    expect(nombreEnLinea(k3, "Relé de seguridad 2 canales")).toBe("Seguridad del recipiente · -K3 · Relé de seguridad 2 canales");
  });

  it("sin rótulo (un servidor anterior), la designación es lo principal y el detalle la sigue", () => {
    expect(nombreEnLinea({ designacion: "-K3" }, "Relé de seguridad 2 canales")).toBe("-K3 · Relé de seguridad 2 canales");
    expect(designacionSecundaria({ designacion: "-K3" })).toBeNull();
  });

  it("un detalle que repite lo principal no se dice dos veces", () => {
    expect(nombreEnLinea({ designacion: "-K1", rotulo: "PLC" }, "PLC")).toBe("PLC · -K1");
  });

  it("Tablero → Aparatos de la mezcladora: los dos relés y los dos pilotos ámbar ya no se leen igual", () => {
    const linea = (des: string) => {
      const a = APARATOS_MEZCLADORA.find((x) => x.designacion === des)!;
      return nombreEnLinea(a, a.nombre);
    };
    expect(linea("-K2")).toBe("Seguridad de parada de emergencia y tapa del tanque · -K2 · Relé de seguridad 2 canales 24 VDC");
    expect(linea("-K3")).toBe("Seguridad de recipiente bajo la descarga · -K3 · Relé de seguridad 2 canales 24 VDC");
    expect(linea("-P3")).toBe("Tapa abierta · -P3 · Piloto LED Ø22 ámbar 24 V");
    expect(linea("-P4")).toBe("Recipiente no acoplado · -P4 · Piloto LED Ø22 ámbar 24 V");
    expect(new Set(APARATOS_MEZCLADORA.filter((a) => a.origen !== "tipo").map((a) => nombrePrincipal(a))).size)
      .toBe(APARATOS_MEZCLADORA.filter((a) => a.origen !== "tipo").length - 1); // «Marcha» = pulsador y piloto (A9)
  });
});

describe("la junta por su pieza hija (D15)", () => {
  it("el nombre de la pieza hija, con el id detrás; sin hija conocida, el id", () => {
    const piezas: Record<string, string> = { c66: "Tapa de carga" };
    const nombre = (id: string) => piezas[id] ?? id;
    expect(nombreEnLinea(nombreDeJunta({ name: "j_tapa_carga", child: "c66" }, nombre))).toBe("Tapa de carga · j_tapa_carga");
    expect(nombreEnLinea(nombreDeJunta({ name: "c388_puerta", child: "c999" }, nombre))).toBe("c388_puerta");
  });
});

describe("la ficha de pieza dice qué aparato es, con lo ya leído", () => {
  it("de la sesión viva, del Tablero o de Neumática, en ese orden; si no es un aparato, nada", () => {
    expect(aparatoDePieza("c400_d_-S1", [INICIO_DEMO.mandos])).toEqual({ designacion: "-S1", rotulo: "Marcha" });
    expect(nombreEnLinea(aparatoDePieza("c400_d_-S1", [INICIO_DEMO.mandos])!)).toBe("Marcha · -S1");
    expect(aparatoDePieza("c400_d_-K3", [null, INICIO_DEMO.mandos, APARATOS_MEZCLADORA]))
      .toEqual({ designacion: "-K3", rotulo: "Seguridad de recipiente bajo la descarga" });
    const neu = aparatosDeNeumatica([{ designacion: "-MM1", piezas: ["c1_cuerpo", "c1_vastago"] }],
      { "-MM1": { rotulo: "Cilindro de compuerta" } });
    expect(aparatoDePieza("c1_vastago", [undefined, neu])).toEqual({ designacion: "-MM1", rotulo: "Cilindro de compuerta" });
    expect(aparatoDePieza("c1_vastago", [aparatosDeNeumatica([{ designacion: "-MM1", piezas: ["c1_vastago"] }], undefined)]))
      .toEqual({ designacion: "-MM1" });
    expect(aparatoDePieza("larguero", [INICIO_DEMO.mandos, PANEL_CON_FALLAS.detalle!.aparatos])).toBeNull();
  });
});

describe("una sola fuente de nombres: el servidor (D13)", () => {
  it("las superficies de F4 no traen tabla de nombres de tipo", () => {
    const superficies = ["vivo/arbolSenales.ts", "vivo/PanelSenales.tsx", "vivo/EventosVivos.tsx", "tablero/DetalleTablero.tsx",
      "neumatica/AccionamientoManual.tsx", "neumatica/VistaNeumatica.tsx", "neumatica/EsquemaNeumatica.tsx",
      "pruebas/VistaPruebas.tsx", "visor/FichaPieza.tsx", "visor/aparatoDePieza.ts", "diseno/nombres.ts"];
    for (const s of superficies) {
      const texto = fuente(s);
      for (const tipo of ["\"Relé de seguridad\"", "\"Electroválvula\"", "\"Seta de emergencia\"", "\"Interruptor de resguardo\"",
        "rele_seguridad:", "electrovalvula:"]) {
        expect(texto, `${s} nombra el tipo ${tipo}`).not.toContain(tipo);
      }
    }
  });
});
