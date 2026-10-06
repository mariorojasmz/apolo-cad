import { describe, expect, it } from "vitest";
import { textoAviso } from "./textoAviso";

/* El aviso cuenta lo que hizo el agente, con singular y plural correctos. */

const ids = (n: number) => Array.from({ length: n }, (_, i) => `c${i + 1}`);
const aviso = (nuevos: number, cambiados: number, eliminados: number) =>
  textoAviso({ nuevos: ids(nuevos), cambiados: ids(cambiados), eliminados });

describe("textoAviso", () => {
  it("sólo cambiadas, en singular y plural", () => {
    expect(aviso(0, 1, 0)).toBe("El agente cambió 1 pieza");
    expect(aviso(0, 4, 0)).toBe("El agente cambió 4 piezas");
  });

  it("sólo nuevas, en singular y plural", () => {
    expect(aviso(1, 0, 0)).toBe("El agente agregó 1 pieza");
    expect(aviso(3, 0, 0)).toBe("El agente agregó 3 piezas");
  });

  it("sólo eliminadas", () => {
    expect(aviso(0, 0, 1)).toBe("El agente eliminó 1 pieza");
    expect(aviso(0, 0, 5)).toBe("El agente eliminó 5 piezas");
  });

  it("mezcla: el sustantivo va en la primera cuenta y la última se une con «y»", () => {
    expect(aviso(0, 2, 1)).toBe("El agente cambió 2 piezas y eliminó 1");
    expect(aviso(2, 1, 0)).toBe("El agente agregó 2 piezas y cambió 1");
    expect(aviso(1, 2, 3)).toBe("El agente agregó 1 pieza, cambió 2 y eliminó 3");
    expect(aviso(3, 0, 1)).toBe("El agente agregó 3 piezas y eliminó 1");
  });

  it("sin nada que contar, vacío", () => {
    expect(aviso(0, 0, 0)).toBe("");
  });
});
