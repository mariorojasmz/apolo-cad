import { describe, expect, it } from "vitest";
import { soloLecturaDe, textoSoloLectura } from "./soloLectura";
import type { SceneOut } from "../types";

/* Sólo lectura de D4 (plan núcleo-abierto-extensiones-privadas): el campo
   `document.solo_lectura = {extensiones, aviso} | null` del payload de escena. */

const escena = (solo_lectura?: unknown) => ({ document: { solo_lectura } }) as unknown as Pick<SceneOut, "document">;

describe("proyecto en sólo lectura", () => {
  it("sin el campo, null o sin escena, se puede editar", () => {
    expect(soloLecturaDe(null)).toBeNull();
    expect(soloLecturaDe(undefined)).toBeNull();
    expect(soloLecturaDe(escena())).toBeNull();
    expect(soloLecturaDe(escena(null))).toBeNull();
  });

  it("un marcador mal formado no bloquea", () => {
    expect(soloLecturaDe(escena("sí"))).toBeNull();
    expect(soloLecturaDe(escena({ aviso: "x" }))).toBeNull();
  });

  it("devuelve el MISMO objeto de la escena (selector estable de zustand)", () => {
    const s = { extensiones: ["hola"], aviso: "Aviso del servidor." };
    expect(soloLecturaDe(escena(s))).toBe(s);
  });

  it("el aviso nombra la extensión que falta y dice qué puedes hacer", () => {
    expect(textoSoloLectura({ extensiones: ["hola"], aviso: "" })).toBe(
      "Este proyecto usa la extensión «hola», que no está instalada: puedes verlo, no editarlo.",
    );
  });

  it("con varias, las enumera en plural", () => {
    expect(textoSoloLectura({ extensiones: ["a", "b", "c"], aviso: "" })).toBe(
      "Este proyecto usa las extensiones «a», «b» y «c», que no están instaladas: puedes verlo, no editarlo.",
    );
  });

  it("sin nombres, usa el aviso del servidor o uno genérico", () => {
    expect(textoSoloLectura({ extensiones: [], aviso: "Aviso del servidor." })).toBe("Aviso del servidor.");
    expect(textoSoloLectura({ extensiones: [], aviso: "" })).toMatch(/puedes verlo, no editarlo/);
  });
});
