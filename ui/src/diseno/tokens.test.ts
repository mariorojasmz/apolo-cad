import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CURVA_SUAVE, MOV_NORMAL_MS, MOV_RAPIDO_MS } from "./movimiento";

/* Los tokens del tema (plan V8.5 D14, F3b-0): existen en styles.css, el movimiento de JS es el
   mismo que el de CSS, con movimiento reducido las duraciones van a 0, y el CSS de `diseno/`
   no trae colores ni tamaños sueltos (sólo tokens). */

const AQUI = dirname(fileURLToPath(import.meta.url));
const estilos = readFileSync(join(AQUI, "..", "styles.css"), "utf8");
const raiz = estilos.slice(estilos.indexOf(":root {"), estilos.indexOf("}", estilos.indexOf(":root {")));
const token = (nombre: string) => raiz.match(new RegExp(`${nombre}:\\s*([^;]+);`))?.[1].trim();

describe("tokens del tema", () => {
  it("tipografía con nombre, espaciado en múltiplos de 4 px y radios", () => {
    for (const n of ["titulo", "subtitulo", "cuerpo", "nota", "cifra"]) {
      expect(token(`--fs-${n}`), `--fs-${n}`).toMatch(/^\d+px$/);
      expect(token(`--fw-${n}`), `--fw-${n}`).toMatch(/^[1-9]00$/);
    }
    const tamanos = ["titulo", "subtitulo", "cuerpo", "nota"].map((n) => parseFloat(token(`--fs-${n}`)!));
    expect([...tamanos].sort((a, b) => b - a)).toEqual(tamanos); // la escala baja en orden
    for (const n of [1, 2, 3, 4, 5, 6, 8]) expect(parseFloat(token(`--sp-${n}`)!) % 4, `--sp-${n}`).toBe(0);
    for (const n of ["--radius-sm", "--radius", "--radius-lg", "--radius-pill"]) expect(token(n), n).toBeTruthy();
  });

  it("el movimiento de CSS y el de JavaScript son el mismo", () => {
    expect(token("--mov-rapido")).toBe(`${MOV_RAPIDO_MS}ms`);
    expect(token("--mov-normal")).toBe(`${MOV_NORMAL_MS}ms`);
    expect(token("--curva-suave")).toBe(`cubic-bezier(${CURVA_SUAVE.join(", ")})`);
  });

  it("con movimiento reducido, lo que anima con los tokens salta", () => {
    const reducido = estilos.slice(estilos.lastIndexOf("@media (prefers-reduced-motion: reduce)"));
    expect(reducido).toMatch(/--mov-rapido:\s*0ms/);
    expect(reducido).toMatch(/--mov-normal:\s*0ms/);
  });

  it("el CSS de diseno/ y de tablero/ usa sólo tokens: sin colores, tamaños de letra ni duraciones sueltas", () => {
    const css = [AQUI, join(AQUI, "..", "tablero")]
      .flatMap((dir) => readdirSync(dir).filter((f) => f.endsWith(".css")).map((f) => join(dir, f)))
      .map((f) => readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, "")).join("\n");
    expect(css).toContain(".tb-fila"); // el panel «Tablero» (V8.5 F3b) entra al control
    expect(css.match(/#[0-9a-f]{3,8}\b|rgba?\(/gi) ?? []).toEqual([]);
    expect(css.match(/font-size:\s*\d/g) ?? []).toEqual([]);
    expect(css.match(/\b\d+m?s\b(?![^(]*\))/g)?.filter((d) => d !== "0s") ?? []).toEqual([]);
  });
});
