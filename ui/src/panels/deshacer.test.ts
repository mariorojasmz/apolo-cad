import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import {
  etiquetasDe, filaConTecla, hayCambios, rotuloAbrir, rotuloLista, textoPie, tituloBoton,
} from "./deshacer";

/* Deshacer y Rehacer dicen qué cambio revierten y, desde la lista, revierten varios de una vez
   (plan deshacer-con-etiqueta, D7). El caso que lo pidió: un arrastre accidental que movió una
   pieza y no saber hasta dónde deshacer. */

const DOC = {
  can_undo: true,
  can_redo: true,
  undo_labels: ["Mover «Guarda tambor motriz»", "Variable «L»: 2000 → 3200", "Caja «Soporte motor»"],
  redo_labels: ["Lote de 33 comandos: 12 nuevos, 21 editados"],
};

describe("tituloBoton", () => {
  it("dice el próximo cambio después del verbo", () => {
    expect(tituloBoton("deshacer", DOC.undo_labels)).toBe("Deshacer: Mover «Guarda tambor motriz»");
    expect(tituloBoton("rehacer", DOC.redo_labels)).toBe("Rehacer: Lote de 33 comandos: 12 nuevos, 21 editados");
  });

  it("sin etiqueta queda el verbo solo, como antes", () => {
    expect(tituloBoton("deshacer", [])).toBe("Deshacer");
    expect(tituloBoton("rehacer", ["  "])).toBe("Rehacer");
  });
});

describe("textoPie", () => {
  it("cuenta los cambios en singular y en plural", () => {
    expect(textoPie("deshacer", 1)).toBe("Deshacer 1 cambio");
    expect(textoPie("deshacer", 3)).toBe("Deshacer 3 cambios");
    expect(textoPie("rehacer", 1)).toBe("Rehacer 1 cambio");
    expect(textoPie("rehacer", 50)).toBe("Rehacer 50 cambios");
  });
});

describe("etiquetasDe y hayCambios", () => {
  it("cada sentido lee su lista, la más próxima primero", () => {
    expect(etiquetasDe(DOC, "deshacer")[0]).toBe("Mover «Guarda tambor motriz»");
    expect(etiquetasDe(DOC, "rehacer")).toEqual(DOC.redo_labels);
  });

  it("una API sin listas (o sin documento) da una lista vacía: el botón sigue andando y el ▾ no abre", () => {
    const viejo = { can_undo: true, can_redo: false };
    expect(etiquetasDe(viejo, "deshacer")).toEqual([]);
    expect(etiquetasDe(undefined, "rehacer")).toEqual([]);
    expect(hayCambios(viejo, "deshacer")).toBe(true);
    expect(hayCambios(viejo, "rehacer")).toBe(false);
    expect(hayCambios(undefined, "deshacer")).toBe(false);
  });
});

describe("rótulos", () => {
  it("el ▾ y la lista se nombran en español", () => {
    expect(rotuloAbrir("deshacer")).toBe("Ver los cambios para deshacer");
    expect(rotuloAbrir("rehacer")).toBe("Ver los cambios para rehacer");
    expect(rotuloLista("deshacer")).toBe("Cambios para deshacer");
  });
});

describe("filaConTecla", () => {
  it("las flechas mueven el foco sin dar la vuelta; Inicio y Fin van a los extremos", () => {
    expect(filaConTecla(0, "ArrowDown", 3)).toBe(1);
    expect(filaConTecla(2, "ArrowDown", 3)).toBe(2);
    expect(filaConTecla(0, "ArrowUp", 3)).toBe(0);
    expect(filaConTecla(2, "ArrowUp", 3)).toBe(1);
    expect(filaConTecla(1, "Home", 3)).toBe(0);
    expect(filaConTecla(0, "End", 3)).toBe(2);
  });

  it("otras teclas (y una lista vacía) no son de la lista", () => {
    expect(filaConTecla(0, "Enter", 3)).toBeNull();
    expect(filaConTecla(0, "Delete", 3)).toBeNull();
    expect(filaConTecla(0, "ArrowDown", 0)).toBeNull();
  });
});

describe("api.undo / api.redo con pasos", () => {
  afterEach(() => vi.unstubAllGlobals());

  const rutas = async (llamar: () => Promise<unknown>) => {
    const fetch = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await llamar();
    return fetch.mock.calls.map((c) => (c as unknown[])[0]);
  };

  it("varios cambios van en ?pasos=N; uno, por la ruta de siempre", async () => {
    expect(await rutas(() => api.undo(3))).toEqual(["/api/undo?pasos=3"]);
    expect(await rutas(() => api.redo(2))).toEqual(["/api/redo?pasos=2"]);
    expect(await rutas(() => api.undo())).toEqual(["/api/undo"]);
    expect(await rutas(() => api.redo(1))).toEqual(["/api/redo"]);
  });
});
