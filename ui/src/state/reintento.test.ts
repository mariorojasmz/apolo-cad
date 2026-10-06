import { describe, expect, it } from "vitest";
import { withRetry } from "./reintento";

/* La sincronización de fondo reintenta un fallo transitorio antes de rendirse. */

/** Una llamada que falla las primeras `fallos` veces y después devuelve «ok». */
function llamada(fallos: number) {
  let veces = 0;
  const run = async () => {
    veces++;
    if (veces <= fallos) throw new Error(`fallo ${veces}`);
    return "ok";
  };
  return { run, veces: () => veces };
}

describe("withRetry", () => {
  it("sin fallo, llama una sola vez", async () => {
    const l = llamada(0);
    await expect(withRetry(l.run, 2, 0)).resolves.toBe("ok");
    expect(l.veces()).toBe(1);
  });

  it("un fallo transitorio se recupera al reintentar", async () => {
    const l = llamada(2);
    await expect(withRetry(l.run, 2, 0)).resolves.toBe("ok");
    expect(l.veces()).toBe(3);
  });

  it("agotados los reintentos, propaga el último error", async () => {
    const l = llamada(5);
    await expect(withRetry(l.run, 2, 0)).rejects.toThrow("fallo 3");
    expect(l.veces()).toBe(3);
  });
});
