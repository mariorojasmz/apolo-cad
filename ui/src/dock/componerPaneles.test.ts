import { describe, expect, it } from "vitest";
import type { LucideIcon } from "lucide-react";
import { componerPaneles, type PanelDef } from "./componerPaneles";
import { EXTENSIONES } from "../extensiones/registro";
import { HERRAMIENTAS, PANELES, esPanel } from "./paneles";
import type { Extension } from "../extensiones/tipos";

/* Paneles = núcleo + extensiones (plan núcleo-abierto-extensiones-privadas, D5). El panel de
   prueba vive en este test, no en `src/extensiones/`. */

const Componente = () => null;
const Icono = (() => null) as unknown as LucideIcon;
const def = (titulo: string): PanelDef => ({ titulo, rotulo: titulo, Componente, icono: Icono });

const NUCLEO = { tree: def("Árbol"), bom: def("BOM"), plc: def("PLC") };
const HERR = ["bom", "plc"] as const;

const hola: Extension = {
  nombre: "hola",
  paneles: [
    { id: "hola.saludo", titulo: "Hola", rotulo: "Hola", Componente, icono: Icono },
    { id: "hola.fijo", titulo: "Fijo", rotulo: "Fijo", Componente, icono: Icono, herramienta: false },
  ],
};

const HOY = ["history", "reqs", "bom", "checks", "kin", "mates", "fisica", "ensamblaje", "boceto", "tablero", "neumatica", "mandos", "senales", "plc"];

describe("paneles del núcleo más los de las extensiones", () => {
  it("con el registro vacío quedan los paneles del núcleo, tal cual", () => {
    const { paneles, herramientas } = componerPaneles(NUCLEO, HERR, []);
    expect(Object.keys(paneles)).toEqual(["tree", "bom", "plc"]);
    expect(paneles.bom).toBe(NUCLEO.bom);
    expect(herramientas).toEqual(["bom", "plc"]);
  });

  it("el bundle del núcleo trae los paneles de hoy y nada más", () => {
    if (EXTENSIONES.length) return; // en el build del paquete privado se suman los suyos
    expect([...HERRAMIENTAS]).toEqual(HOY);
    expect(Object.keys(PANELES).sort()).toEqual([...HOY, "tree", "properties", "chat"].sort());
    for (const p of Object.values(PANELES)) expect(p.icono).toBeTruthy();
  });

  it("un panel registrado aparece en PANELES y, si es herramienta, detrás de las del núcleo", () => {
    const { paneles, herramientas } = componerPaneles(NUCLEO, HERR, [hola]);
    expect(paneles["hola.saludo"]).toMatchObject({ titulo: "Hola", rotulo: "Hola", Componente, icono: Icono });
    expect(paneles["hola.fijo"].titulo).toBe("Fijo");
    expect(herramientas).toEqual(["bom", "plc", "hola.saludo"]);
  });

  it("el ancho que pide un panel de extensión llega a PANELES; sin él, no aparece", () => {
    const lamina: Extension = {
      nombre: "planos",
      paneles: [{ id: "planos.hoja", titulo: "Hoja", rotulo: "Hoja", Componente, icono: Icono, ancho: "lamina" }],
    };
    const { paneles } = componerPaneles(NUCLEO, HERR, [hola, lamina]);
    expect(paneles["planos.hoja"].ancho).toBe("lamina");
    expect("ancho" in paneles["hola.saludo"]).toBe(false);
  });

  it("no toca el objeto del núcleo", () => {
    componerPaneles(NUCLEO, HERR, [hola]);
    expect(Object.keys(NUCLEO)).toEqual(["tree", "bom", "plc"]);
  });

  it("esPanel valida un id suelto (layout guardado, cajón del visor)", () => {
    expect(esPanel("bom")).toBe(true);
    expect(esPanel("hola.saludo")).toBe(EXTENSIONES.some((e) => e.paneles?.some((p) => p.id === "hola.saludo")));
    expect(esPanel("toString")).toBe(false);
  });
});
