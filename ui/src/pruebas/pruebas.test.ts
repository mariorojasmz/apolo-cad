import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AHORA_MUESTRARIO, CORRIDAS_DEMO, DETALLE_PRUEBA, PANEL_PRUEBAS } from "../diseno/muestrario/datosPruebas";
import VistaPruebas from "./VistaPruebas";
import { duracion, estadoDeFila, fechaCorta, lineaBajo, progresoCorrida, textoIncidencia, tituloPrueba } from "./vista";

/* Lo que dice el panel «Pruebas» (plan visor-para-evaluar D3–D5). */

describe("fechaCorta", () => {
  const ahora = new Date(2026, 9, 26, 18, 0);
  it("hoy, ayer y otro día (con el año sólo si no es este)", () => {
    expect(fechaCorta("2026-10-26T14:03:09", ahora)).toBe("hoy, 14:03");
    expect(fechaCorta("2026-10-25T09:10:00", ahora)).toBe("ayer, 09:10");
    expect(fechaCorta("2026-10-02T07:05:00", ahora)).toBe("2 oct, 07:05");
    expect(fechaCorta("2025-12-31T23:59:00", ahora)).toBe("31 dic 2025, 23:59");
  });
  it("sin fecha o con una rota, nada", () => {
    expect(fechaCorta(undefined, ahora)).toBe("");
    expect(fechaCorta("ayer", ahora)).toBe("");
  });
});

describe("progreso de una corrida", () => {
  it("en la cola no hay fracción; corriendo, con lo que tardó la última vez", () => {
    expect(progresoCorrida({ jobId: "j", estado: "encolado", desde: null }, 0)).toEqual({
      frase: "En espera: otra prueba está corriendo", fraccion: null,
    });
    const c = { jobId: "j", estado: "corriendo" as const, desde: 0, estimadoS: 40 };
    expect(progresoCorrida(c, 10_000)).toEqual({ frase: "Corriendo · 10 s de unos 40 s", fraccion: 0.25 });
    expect(progresoCorrida(c, 90_000).fraccion).toBe(0.95); // nunca se completa sola
    expect(progresoCorrida({ ...c, estimadoS: undefined }, 5_000)).toEqual({ frase: "Corriendo · 5 s", fraccion: null });
  });
  it("duraciones legibles", () => {
    expect(duracion(9.6)).toBe("10 s");
    expect(duracion(100)).toBe("1 min 40 s");
    expect(duracion(600)).toBe("10 min");
  });
});

describe("tituloPrueba", () => {
  it("el título humanizado del servidor; el id sólo si no lo trae (nombres-por-funcion D14)", () => {
    expect(tituloPrueba({ nombre: "descargar_sin_recipiente", titulo: "Descargar sin recipiente" })).toBe("Descargar sin recipiente");
    expect(tituloPrueba({ nombre: "marcha nominal" })).toBe("marcha nominal");
  });
});

describe("la fila mientras corre y lo que no cumplió (nombres-por-funcion F5b)", () => {
  const ahora = new Date(2026, 9, 26, 18, 0);
  const falla = { nombre: "descargar", titulo: "Descargar", estado: "falla", rotulo: "Falla", severidad: "falla" as const,
    fecha: "2026-10-26T14:03:00" };

  it("corriendo dice «Corriendo» (o «En espera»), nunca el «Pasa»/«Falla» viejo", () => {
    expect(estadoDeFila(falla)).toEqual({ rotulo: "Falla", severidad: "falla" });
    expect(estadoDeFila(falla, { estado: "corriendo", desde: 0 })).toEqual({ rotulo: "Corriendo", severidad: "sin_evaluar" });
    expect(estadoDeFila(falla, { estado: "encolado", desde: null })).toEqual({ rotulo: "En espera", severidad: "sin_evaluar" });
  });

  it("debajo: la fecha; vencida, lo que toca; sin correr, nada (el estado ya lo dice una vez)", () => {
    expect(lineaBajo(falla, ahora)).toBe("hoy, 14:03");
    expect(lineaBajo({ ...falla, estado: "vencido" }, ahora)).toBe("Hay que volver a correrla");
    expect(lineaBajo({ estado: "sin_correr" }, ahora)).toBe("");
    expect(lineaBajo(falla, ahora, true)).toBe(""); // corriendo, lo dice la barra
  });

  it("en pantalla: «Corriendo» sin el estado viejo, un solo «sin correr» y la frase llana sobre la expresión", () => {
    const acciones = { alternar: () => {}, correr: () => {}, enVivo: () => {}, verLugar: () => {} };
    const html = renderToStaticMarkup(createElement(VistaPruebas, {
      panel: PANEL_PRUEBAS, abierto: DETALLE_PRUEBA.nombre, detalle: DETALLE_PRUEBA, corridas: {
        ...CORRIDAS_DEMO, [DETALLE_PRUEBA.nombre]: CORRIDAS_DEMO.ciclo_nominal }, fallos: {}, acciones, ahora: AHORA_MUESTRARIO }));
    const fila = (titulo: string) => html.slice(html.indexOf(`pr-nombre">${titulo}<`), html.indexOf("</button>", html.indexOf(`pr-nombre">${titulo}<`)));
    expect(fila("Ciclo nominal")).toContain('pr-estado">Corriendo<');
    expect(fila("Ciclo nominal")).not.toContain(">Pasa<");
    expect(fila("Descargar sin recipiente")).not.toContain(">Falla<");
    expect(html).not.toContain("Todavía no se corrió");
    expect(html.match(/>Sin correr</g)).toHaveLength(1); // en pantalla, una sola vez (el lector la oye en su fila)
    expect(fila("Abrir tapa en marcha")).toContain("Hay que volver a correrla");
    const pedido = html.indexOf("pr-pedido\">La carrera del cilindro de compuerta (-MM1)");
    expect(pedido).toBeGreaterThan(0);
    // la expresión cruda, sólo dentro de «Detalle técnico» y después de la frase
    expect(html.indexOf("-MM1.x_mm &lt; 5 siempre")).toBeGreaterThan(html.indexOf("Detalle técnico"));
    expect(html).not.toContain('pr-asercion">');
  });
});

describe("textoIncidencia", () => {
  it("producto, qué le pasó, dónde (la pieza o el punto) y a qué hora", () => {
    expect(textoIncidencia({ tipo: "trabados", producto: "caja 3", que: "trabado", hora_s: 12.4, cerca_de: "Banda" }))
      .toBe("caja 3 trabado cerca de «Banda» a los 12 s");
    expect(textoIncidencia({ tipo: "perdidos", producto: "caja 1", que: "cayó al piso", hora_s: 3.25, punto_mm: [1200, -340, 0] }))
      .toBe("caja 1 cayó al piso en (1 200; −340; 0) mm a los 3,3 s");
    expect(textoIncidencia({ tipo: "trabados", mas: 4 })).toBe("y 4 más");
  });
});
