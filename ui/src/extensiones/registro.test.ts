import { describe, expect, it } from "vitest";
import { EXTENSIONES, validarExtensiones } from "./registro";

/* El registro de extensiones de la UI (plan núcleo-abierto-extensiones-privadas, D5). La
   extensión de prueba vive AQUÍ, no en `src/extensiones/<nombre>/`: el núcleo publica el
   registro vacío. */

const Componente = () => null;
const Icono = (() => null) as unknown as import("lucide-react").LucideIcon;

const panel = (id: string, extra: Record<string, unknown> = {}) => ({
  id, titulo: "Hola", rotulo: "Hola", Componente, icono: Icono, ...extra,
});

describe("registro de extensiones de la UI", () => {
  it("lo que compila este bundle es válido (en el núcleo, nada)", () => {
    // en un checkout del núcleo no hay carpetas en src/extensiones/; en el del paquete privado,
    // las suyas: este caso pasa en los dos y rompe si alguna está mal formada
    expect(Array.isArray(EXTENSIONES)).toBe(true);
    for (const ext of EXTENSIONES) expect(ext.nombre).toMatch(/^[a-z][a-z0-9_-]*$/);
  });

  it("sin carpetas, el registro queda vacío", () => {
    expect(validarExtensiones({})).toEqual([]);
  });

  it("recoge cada carpeta y las ordena por nombre", () => {
    const zeta = { nombre: "zeta", paneles: [panel("zeta.uno")] };
    const hola = { nombre: "hola", paneles: [panel("hola.saludo")] };
    const out = validarExtensiones({ "./zeta/index.ts": { default: zeta }, "./hola/index.tsx": { default: hola } });
    expect(out.map((e) => e.nombre)).toEqual(["hola", "zeta"]);
    expect(out[0]).toBe(hola);
  });

  it("una extensión sin paneles es válida (los campos crecen opcionales)", () => {
    expect(validarExtensiones({ "./vacia/index.ts": { default: { nombre: "vacia" } } })).toHaveLength(1);
  });

  it("rechaza el nombre que no es el de su carpeta", () => {
    expect(() => validarExtensiones({ "./hola/index.ts": { default: { nombre: "otra" } } })).toThrow(/su carpeta/);
  });

  it("rechaza un index sin export por defecto", () => {
    expect(() => validarExtensiones({ "./hola/index.ts": {} })).toThrow(/no exporta/);
  });

  it("rechaza un panel sin el prefijo de su extensión", () => {
    for (const id of ["saludo", "otra.saludo", "hola.", "hola.Con Espacio"]) {
      const m = { "./hola/index.ts": { default: { nombre: "hola", paneles: [panel(id)] } } };
      expect(() => validarExtensiones(m), id).toThrow(/tiene que llamarse «hola\.<panel>»/);
    }
  });

  it("rechaza un panel sin título, componente o ícono", () => {
    const sin = (extra: Record<string, unknown>) => ({
      "./hola/index.ts": { default: { nombre: "hola", paneles: [panel("hola.saludo", extra)] } },
    });
    expect(() => validarExtensiones(sin({ titulo: "" }))).toThrow(/título o rótulo/);
    expect(() => validarExtensiones(sin({ icono: undefined }))).toThrow(/componente o el ícono/);
    expect(() => validarExtensiones(sin({ Componente: undefined }))).toThrow(/componente o el ícono/);
  });

  it("rechaza un id de panel repetido y junta todos los problemas en un mensaje", () => {
    const m = {
      "./hola/index.ts": { default: { nombre: "hola", paneles: [panel("hola.a"), panel("hola.a")] } },
      "./mal/index.ts": { default: { nombre: "otro" } },
    };
    expect(() => validarExtensiones(m)).toThrow(/hola: el panel «hola\.a» está repetido[\s\S]*mal: el nombre/);
  });
});
