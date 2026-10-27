import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ordenarItems, queAtender, veredictoDe, type ItemAtencion } from "./atencion";
import { cifra } from "./cifra";
import { avance, decimalesDelPaso, textoDeslizador } from "./valorDeslizador";
import { curvaBezier, MOV_NORMAL_MS, suave } from "./movimiento";
import Deslizador from "./Deslizador";
import EstadoVacio from "./EstadoVacio";
import ItemsAtencion from "./ItemsAtencion";
import Veredicto from "./Veredicto";

/* Las piezas comunes de diseño (plan V8.5 F3b-0), con el caso de ejemplo del panel «Tablero»
   que va a usar F3b (los mismos datos que el muestrario, `muestrario/datos.ts`). */
import { ITEMS_TABLERO } from "./muestrario/datos";

describe("cifra", () => {
  it("coma decimal, espacio de miles, unidad separada y grados pegados", () => {
    expect(cifra(1799, 0, "rpm")).toBe("1 799\u00a0rpm");
    expect(cifra(3.814, 2, "A")).toBe("3,81\u00a0A");
    expect(cifra(64, 0, "%")).toBe("64\u00a0%");
    expect(cifra(90, 0, "°")).toBe("90°");
    expect(cifra(-2.5, 1)).toBe("−2,5");
    expect(cifra(-0.001, 1)).toBe("0,0");
  });
  it("sin valor, una raya", () => {
    expect(cifra(undefined)).toBe("—");
    expect(cifra(null)).toBe("—");
    expect(cifra(Number.NaN, 2, "mm")).toBe("—");
  });
});

describe("veredicto e ítems de atención", () => {
  const it_ = (clave: string, severidad: ItemAtencion["severidad"]): ItemAtencion => ({ clave, severidad, frase: clave });

  it("sin nada que atender, la frase del panel", () => {
    expect(veredictoDe([], "El tablero cumple")).toEqual({ severidad: "bien", frase: "El tablero cumple" });
    expect(veredictoDe([it_("a", "bien")], "El tablero cumple").severidad).toBe("bien");
  });

  it("cuenta lo que hay que corregir y lo que hay que revisar", () => {
    expect(veredictoDe([it_("a", "aviso")], "x").frase).toBe("1 cosa por revisar");
    expect(veredictoDe([it_("a", "aviso"), it_("b", "aviso")], "x").frase).toBe("2 cosas por revisar");
    const mixto = veredictoDe([it_("a", "aviso"), it_("b", "falla"), it_("c", "aviso")], "x");
    expect(mixto).toEqual({ severidad: "falla", frase: "1 cosa por corregir y 2 por revisar" });
    expect(veredictoDe([it_("a", "falla"), it_("b", "sin_evaluar")], "x").frase).toBe("1 cosa por corregir");
    // sólo lo sin evaluar: cumple lo revisado, sin decir que cumple todo (V8.5 F3b)
    expect(veredictoDe([it_("a", "sin_evaluar")], "x")).toEqual({ severidad: "bien", frase: "Cumple lo que revisamos" });
    expect(veredictoDe([it_("a", "sin_evaluar")], "x", "y").frase).toBe("y");
  });

  it("lo más grave primero, estable a igual severidad; lo que cumple no pide atención", () => {
    const items = [it_("a1", "aviso"), it_("s", "sin_evaluar"), it_("f", "falla"), it_("a2", "aviso"), it_("b", "bien")];
    expect(ordenarItems(items).map((x) => x.clave)).toEqual(["f", "a1", "a2", "s", "b"]);
    expect(queAtender(items).map((x) => x.clave)).toEqual(["f", "a1", "a2", "s"]);
  });

  it("el caso del tablero: veredicto, filas con cifra y botón cuando hay acción", () => {
    const v = veredictoDe(ITEMS_TABLERO, "El tablero cumple");
    const html = renderToStaticMarkup(h("div", null,
      h(Veredicto, { ...v, nota: "Revisamos 14 reglas" }),
      h(ItemsAtencion, { items: queAtender(ITEMS_TABLERO), rotulo: "Lo que pide atención en el tablero" })));
    expect(html).toContain(v.frase);
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain("64\u00a0%");
    expect(html).toContain('aria-label="Para revisar: ');
    expect(html).toContain('role="img" aria-label="Para corregir"'); // el ícono se dice, no sólo se ve
    const conAccion = queAtender(ITEMS_TABLERO).filter((x) => x.accion).length;
    expect(html.match(/<button type="button" class="ia-fila"/g)?.length).toBe(conAccion);
  });

  it("sin ítems, la lista no se dibuja", () => {
    expect(renderToStaticMarkup(h(ItemsAtencion, { items: [], rotulo: "x" }))).toBe("");
  });
});

describe("estado vacío", () => {
  it("qué va a aparecer, cómo empezar y la acción", () => {
    const onClick = vi.fn();
    const html = renderToStaticMarkup(h(EstadoVacio, {
      titulo: "Aquí vas a ver el tablero armado", accion: { rotulo: "Copiar el pedido", onClick },
    }, "Pídele al agente que lo arme desde el circuito."));
    expect(html).toContain('class="ev-titulo">Aquí vas a ver el tablero armado');
    expect(html).toContain("Pídele al agente");
    expect(html).toContain('<button type="button" class="primary ev-accion">Copiar el pedido</button>');
  });
});

describe("deslizador", () => {
  it("la pista llena hasta el valor, acotada", () => {
    expect(avance(45, 0, 90)).toBe(50);
    expect(avance(-10, 0, 90)).toBe(0);
    expect(avance(200, 0, 90)).toBe(100);
    expect(avance(5, 5, 5)).toBe(0);
  });
  it("los decimales salen del paso y el valor se lee con su unidad", () => {
    expect(decimalesDelPaso(1)).toBe(0);
    expect(decimalesDelPaso(0.1)).toBe(1);
    expect(decimalesDelPaso(0.25)).toBe(2);
    expect(textoDeslizador(90, 1, "°")).toBe("90°");
    expect(textoDeslizador(45.5, 0.5, "mm")).toBe("45,5\u00a0mm");
    expect(textoDeslizador(0.333, 0.01)).toBe("0,33");
  });
  it("rótulo asociado y valor con unidad para el lector; compacto deja el rótulo en aria-label", () => {
    const pleno = renderToStaticMarkup(h(Deslizador, { rotulo: "Puerta", valor: 90, min: 0, max: 110, unidad: "°", onCambio: () => {} }));
    expect(pleno).toMatch(/<label for="([^"]+)">Puerta<\/label>/);
    expect(pleno).toContain('aria-valuetext="90°"');
    expect(pleno).toContain('type="range"');
    const compacto = renderToStaticMarkup(h(Deslizador, { compacto: true, rotulo: "Posición del corte", valor: 30, min: 0, max: 100, unidad: "%", onCambio: () => {} }));
    expect(compacto).not.toContain("<label");
    expect(compacto).toContain('aria-label="Posición del corte"');
    expect(compacto).toContain('aria-valuetext="30\u00a0%"');
  });
});

describe("movimiento", () => {
  it("la curva suave arranca y termina quieta, y es monótona", () => {
    expect(suave(0)).toBe(0);
    expect(suave(1)).toBe(1);
    expect(suave(0.5)).toBeGreaterThan(0.6); // cubic-bezier(0.4, 0, 0.2, 1) va adelantada a la mitad
    expect(suave(0.05)).toBeLessThan(0.05); // arranca suave
    let antes = 0;
    for (let i = 1; i <= 100; i++) {
      const y = suave(i / 100);
      expect(y).toBeGreaterThanOrEqual(antes);
      antes = y;
    }
  });
  it("la recta es la identidad y la duración normal está en 250–400 ms", () => {
    const recta = curvaBezier(0, 0, 1, 1);
    expect(recta(0.3)).toBeCloseTo(0.3, 5);
    expect(MOV_NORMAL_MS).toBeGreaterThanOrEqual(250);
    expect(MOV_NORMAL_MS).toBeLessThanOrEqual(400);
  });
});
