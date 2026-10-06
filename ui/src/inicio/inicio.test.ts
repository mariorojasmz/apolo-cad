import { describe, expect, it } from "vitest";
import { diasAtras, fechaCorta, fechaLarga, grupoFecha } from "./fechas";
import { agrupar, coincide, filtrarYOrdenar, normalizar, palabras, resaltar } from "./proyectos";
import type { ProjectInfo } from "../types";

const AHORA = new Date(2026, 9, 6, 13, 30); // 6 oct 2026, 13:30 local

const p = (id: number, name: string, updated_at: string, pieces = 1): ProjectInfo => ({ id, name, updated_at, pieces });

describe("fechas", () => {
  it("hoy y ayer llevan la hora", () => {
    expect(fechaCorta("2026-10-06T09:18:15", AHORA)).toBe("hoy 09:18");
    expect(fechaCorta("2026-10-05T22:39:50", AHORA)).toBe("ayer 22:39");
  });
  it("este año va sin año; otro año, con año", () => {
    expect(fechaCorta("2026-08-02T00:59:16", AHORA)).toBe("2 ago");
    expect(fechaCorta("2025-06-15T22:39:42", AHORA)).toBe("15 jun 2025");
  });
  it("un texto que no es fecha vuelve tal cual", () => {
    expect(fechaCorta("pronto", AHORA)).toBe("pronto");
    expect(fechaLarga("2026-10-06T09:18:15")).toBe("6 oct 2026, 09:18");
  });
  it("cuenta días de calendario, no horas", () => {
    expect(diasAtras(new Date(2026, 9, 5, 23, 59), AHORA)).toBe(1);
    expect(diasAtras(new Date(2026, 9, 6, 0, 1), AHORA)).toBe(0);
  });
  it("agrupa en tramos", () => {
    expect(grupoFecha("2026-10-06T01:00:00", AHORA)).toBe("Hoy");
    expect(grupoFecha("2026-10-01T01:00:00", AHORA)).toBe("Últimos 7 días");
    expect(grupoFecha("2026-09-10T01:00:00", AHORA)).toBe("Últimos 30 días");
    expect(grupoFecha("2026-07-01T01:00:00", AHORA)).toBe("Anteriores");
  });
});

describe("búsqueda", () => {
  it("ignora mayúsculas y tildes", () => {
    expect(normalizar("Paquetería")).toBe("paqueteria");
    expect(coincide("Puerta Plegable", palabras("PLEGÁBLE"))).toBe(true);
  });
  it("cada palabra en cualquier orden", () => {
    expect(coincide("faja-paqueteria-4m", palabras("4m faja"))).toBe(true);
    expect(coincide("faja-paqueteria-4m", palabras("faja camastro"))).toBe(false);
  });
  it("filtra y ordena", () => {
    const lista = [p(1, "b-uno", "2026-01-01T00:00:00"), p(2, "a-dos", "2026-03-01T00:00:00"), p(3, "c-tres", "2026-02-01T00:00:00")];
    expect(filtrarYOrdenar(lista, "", "recientes").map((x) => x.id)).toEqual([2, 3, 1]);
    expect(filtrarYOrdenar(lista, "", "nombre").map((x) => x.id)).toEqual([2, 1, 3]);
    expect(filtrarYOrdenar(lista, "tres", "recientes").map((x) => x.id)).toEqual([3]);
  });
  it("el orden por nombre respeta los números", () => {
    const lista = [p(1, "rodillo 10", "x"), p(2, "rodillo 2", "x")];
    expect(filtrarYOrdenar(lista, "", "nombre").map((x) => x.id)).toEqual([2, 1]);
  });
});

describe("agrupar", () => {
  const lista = [
    p(1, "abierto", "2026-08-01T00:00:00"),
    p(2, "de-hoy", "2026-10-06T08:00:00"),
    p(3, "viejo", "2026-06-01T00:00:00"),
  ];
  it("el abierto arriba y el resto por tramo", () => {
    const g = agrupar(lista, 1, true, AHORA);
    expect(g.map((x) => x.titulo)).toEqual(["Abierto ahora", "Hoy", "Anteriores"]);
    expect(g[0].proyectos[0].id).toBe(1);
  });
  it("sin agrupar, un solo grupo sin título; vacío, ninguno", () => {
    expect(agrupar(lista, 1, false, AHORA)).toEqual([{ titulo: null, proyectos: lista }]);
    expect(agrupar([], null, true, AHORA)).toEqual([]);
  });
});

describe("resaltar", () => {
  it("marca lo que coincide y conserva el texto original", () => {
    const t = resaltar("Faja-Paquetería-4m", palabras("paqueteria 4m"));
    expect(t.map((x) => x.texto).join("")).toBe("Faja-Paquetería-4m");
    expect(t.filter((x) => x.marca).map((x) => x.texto)).toEqual(["Paquetería", "4m"]);
  });
  it("sin búsqueda, un solo tramo sin marca", () => {
    expect(resaltar("faja", [])).toEqual([{ texto: "faja", marca: false }]);
  });
});
