import { describe, expect, it } from "vitest";
import type { CommandSchema, Pestana } from "../types";
import { pestanasDe } from "./pestanas";

/* Las pestañas del ribbon se derivan de los schemas de la vista persona. Los `orden` y
   rótulos son los de `core/apolo/commands/pistas.py::PESTANAS`. */

const PESTANAS: Record<string, Pestana | null> = {
  crear: { orden: 1, rotulo: "Crear" },
  croquis: { orden: 2, rotulo: "Croquis" },
  superficies: { orden: 3, rotulo: "Superficies" },
  modificar: { orden: 4, rotulo: "Modificar" },
  ensamblaje: { orden: 5, rotulo: "Ensamblar" },
  biblioteca: { orden: 6, rotulo: "Biblioteca" },
  robotica: { orden: 7, rotulo: "Robótica" },
  variables: null,
};

const comando = (type: string, category: string): CommandSchema => ({
  type,
  title: type,
  category,
  kind: "scene",
  pestana: PESTANAS[category],
  pista: "Hace algo.",
  detalle: "",
  schema: {},
});

// En el orden en que llegan del servidor (el del registro, no el de las pestañas).
const SCHEMAS = [
  comando("create_box", "crear"),
  comando("sketch_extrude", "croquis"),
  comando("boundary_surface", "superficies"),
  comando("fill_surface", "superficies"),
  comando("thicken", "superficies"),
  comando("create_revolve", "crear"),
  comando("insert_component", "biblioteca"),
  comando("add_mate", "ensamblaje"),
  comando("drill_hole", "modificar"),
  comando("set_variable", "variables"),
];

describe("pestanasDe", () => {
  it("la pestaña Superficies aparece con su rótulo, en su lugar y con sus 3 comandos", () => {
    const pestanas = pestanasDe(SCHEMAS);
    expect(pestanas.map((p) => p.rotulo)).toEqual(["Crear", "Croquis", "Superficies", "Modificar", "Ensamblar", "Biblioteca"]);
    const sup = pestanas.find((p) => p.clave === "superficies");
    expect(sup?.comandos.map((c) => c.type)).toEqual(["boundary_surface", "fill_surface", "thicken"]);
  });

  it("un comando sin pestaña (pestana: null) no va al ribbon", () => {
    const pestanas = pestanasDe(SCHEMAS);
    expect(pestanas.map((p) => p.clave)).not.toContain("variables");
    expect(pestanas.flatMap((p) => p.comandos.map((c) => c.type))).not.toContain("set_variable");
  });

  it("una categoría sin comandos no tiene pestaña", () => {
    // Robótica tiene pestaña en el servidor, pero en esta lista no llega ningún comando suyo.
    expect(pestanasDe(SCHEMAS).map((p) => p.clave)).not.toContain("robotica");
    expect(pestanasDe([])).toEqual([]);
  });

  it("dentro de una pestaña, los comandos quedan en el orden del servidor", () => {
    const crear = pestanasDe(SCHEMAS).find((p) => p.clave === "crear");
    expect(crear?.comandos.map((c) => c.type)).toEqual(["create_box", "create_revolve"]);
  });
});
