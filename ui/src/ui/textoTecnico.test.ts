import { isValidElement, type ReactElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { textoTecnico } from "./textoTecnico";

/* El texto técnico del servidor (detalle de un comando, ⓘ de un campo) llega como texto
   plano: aquí se prueba la forma que le da la UI, sin DOM, mirando los elementos. */

type El = ReactElement<{ children?: ReactNode }>;

const elementos = (n: ReactNode): El[] => (Array.isArray(n) ? n : [n]).filter(isValidElement) as El[];

/** Lo que se lee: el texto de un nodo sin etiquetas. */
function leido(n: ReactNode): string {
  if (typeof n === "string" || typeof n === "number") return String(n);
  if (Array.isArray(n)) return n.map(leido).join("");
  if (isValidElement(n)) return leido((n as El).props.children);
  return "";
}

const etiquetas = (n: ReactNode) => elementos(n).map((e) => (typeof e.type === "string" ? e.type : "fragmento"));
const codigos = (n: ReactNode) => elementos(n).filter((e) => e.type === "code").map(leido);

describe("textoTecnico", () => {
  it("lo que va entre backticks es código y el texto se lee igual", () => {
    const n = textoTecnico("{u,v} mm desde el centro; solo con `cara` (ignora `diameter`).");
    expect(leido(n)).toBe("{u,v} mm desde el centro; solo con cara (ignora diameter).");
    expect(codigos(n)).toEqual(["cara", "diameter"]);
  });

  it("un backtick sin pareja queda literal", () => {
    const n = textoTecnico("a `b` c `d");
    expect(leido(n)).toBe("a b c `d");
    expect(codigos(n)).toEqual(["b"]);
  });

  it("una línea sola va sin envoltorio, para caber en cualquier bloque", () => {
    expect(etiquetas(textoTecnico("mm, 0 = pasante"))).toEqual(["fragmento"]);
  });

  it("respeta párrafos y viñetas, y la línea que sigue a una lista la cierra", () => {
    const n = textoTecnico("Rodillo de cola.\n\nCÓMO MONTAR:\n- con `position` en la cola\n- sin rotar\nEditar regenera todo.");
    expect(etiquetas(n)).toEqual(["p", "p", "ul", "p"]);
    const lista = elementos(n)[2];
    expect(elementos(lista.props.children).map(leido)).toEqual(["con position en la cola", "sin rotar"]);
  });
});
