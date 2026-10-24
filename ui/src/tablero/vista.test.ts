import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import VacioTablero from "./VacioTablero";
import VistaTablero from "./VistaTablero";
import { veredictoDe } from "../diseno/atencion";
import { PANEL_CON_FALLAS, PANEL_EN_ORDEN, PANEL_SIN_ARMAR } from "../diseno/muestrario/datosTablero";
import type { ItemTablero } from "./tipos";
import {
  accionPuerta, alElegir, cifraDe, conductoresListados, duracionPuerta, itemsDeAtencion, largoConductor,
  perdidasDeclaradas, recorridoDe, rotuloConductor, valorPuertaEn,
} from "./vista";

/* La lógica pura del panel «Tablero» (plan V8.5 F3b): cifras, qué hace cada clic, qué conductores
   se listan, el recorrido que se dibuja y la puerta animada. Los datos son los del muestrario. */

const item = (p: Partial<ItemTablero>): ItemTablero =>
  ({ clave: "x", severidad: "aviso", frase: "Algo", piezas: [], conductores: [], ...p });

function acciones() {
  return { encuadrar: vi.fn(), elegir: vi.fn(), dibujar: vi.fn() };
}

describe("panel Tablero", () => {
  it("escribe la cifra de cada ítem con coma decimal y su unidad", () => {
    expect(cifraDe({ valor: 64, unidad: "%" })).toBe("64 %");
    expect(cifraDe({ valor: 28.32, unidad: "m", decimales: 1 })).toBe("28,3 m");
    expect(cifraDe({ valor: 110, unidad: "°" })).toBe("110°");
    expect(cifraDe({ valor: 10 })).toBe("10");
    expect(cifraDe({})).toBeUndefined();
  });

  it("un ítem con un conductor lo dibuja; con varios, los lista y no dibuja ninguno", () => {
    const a = acciones();
    alElegir(item({ piezas: ["c1_d_F1"], conductores: ["c9"] }), a);
    expect(a.dibujar).toHaveBeenCalledWith("c9");
    expect(a.encuadrar).toHaveBeenCalledWith(["c1_d_F1"], undefined);
    // con el panel, el encuadre también muestra el recorrido entero del conductor
    const c = PANEL_CON_FALLAS.detalle!.conductores[0];
    const con = acciones();
    alElegir(item({ piezas: ["x"], conductores: [c.id] }), con, PANEL_CON_FALLAS);
    expect(con.encuadrar).toHaveBeenCalledWith(["x"], c.recorrido!.flat());
    const b = acciones();
    alElegir(item({ piezas: ["p1", "p2"], conductores: ["c9", "c10"] }), b);
    expect(b.dibujar).toHaveBeenCalledWith(null);
    expect(b.elegir).toHaveBeenCalledOnce();
  });

  it("sin piezas no encuadra; sin nada que mostrar no es botón", () => {
    const a = acciones();
    alElegir(item({ detalle: "Falta la norma" }), a);
    expect(a.encuadrar).not.toHaveBeenCalled();
    const [mudo, conDetalle] = itemsDeAtencion([item({ clave: "a" }), item({ clave: "b", detalle: "x" })], a);
    expect(mudo.accion).toBeUndefined();
    expect(conDetalle.accion).toBeTypeOf("function");
  });

  it("el veredicto del servidor es el que daría la UI con los mismos ítems", () => {
    for (const p of [PANEL_CON_FALLAS, PANEL_EN_ORDEN]) { // sin armar: el servidor lo dice con su frase
      const v = veredictoDe(p.items, "El tablero cumple", "El tablero cumple lo que revisamos");
      expect({ severidad: p.veredicto.severidad, frase: p.veredicto.frase }).toEqual(v);
    }
  });

  it("filtra los conductores del ítem elegido, en su orden", () => {
    const ids = PANEL_CON_FALLAS.items.find((x) => x.clave === "largos")!.conductores;
    const lista = conductoresListados(PANEL_CON_FALLAS, ids);
    expect(lista.map((c) => c.id)).toEqual(PANEL_CON_FALLAS.detalle!.conductores.filter((c) => ids.includes(c.id)).map((c) => c.id));
    expect(conductoresListados(PANEL_CON_FALLAS, null)).toHaveLength(PANEL_CON_FALLAS.detalle!.conductores.length);
  });

  it("rótulo y largo de un conductor", () => {
    const c = PANEL_CON_FALLAS.detalle!.conductores[0];
    expect(rotuloConductor(c)).toBe(c.puntos.join(" → "));
    expect(largoConductor({ ...c, largo_m: 0.4912 })).toBe("0,49 m");
  });

  it("dibuja sólo el conductor elegido y sólo si tiene recorrido", () => {
    const c = PANEL_CON_FALLAS.detalle!.conductores[0];
    expect(recorridoDe(PANEL_CON_FALLAS, c.id)).toBe(c.recorrido);
    expect(recorridoDe(PANEL_CON_FALLAS, null)).toBeNull();
    expect(recorridoDe(PANEL_CON_FALLAS, "no-existe")).toBeNull();
    expect(recorridoDe(null, c.id)).toBeNull();
  });

  it("la puerta se anima con la curva suave y salta con movimiento reducido", () => {
    expect(valorPuertaEn(0, 110, 0)).toBe(0);
    expect(valorPuertaEn(0, 110, 1)).toBe(110);
    expect(valorPuertaEn(0, 110, 2)).toBe(110);
    const mitad = valorPuertaEn(0, 110, 0.5);
    expect(mitad).toBeGreaterThan(55); // arranca suave y frena suave: a la mitad del tiempo ya pasó la mitad
    expect(mitad).toBeLessThan(110);
    expect(valorPuertaEn(110, 0, 1)).toBe(0);
    expect(duracionPuerta(true)).toBe(0);
    expect(duracionPuerta(false)).toBeGreaterThanOrEqual(250);
    expect(duracionPuerta(false)).toBeLessThanOrEqual(400);
  });

  it("el botón abre la puerta cerrada y cierra la abierta", () => {
    expect(accionPuerta(0, 110)).toEqual({ rotulo: "Abrir", destino: 110 });
    expect(accionPuerta(90, 110)).toEqual({ rotulo: "Cerrar", destino: 0 });
  });

  it("dice las pérdidas declaradas y cuántos aparatos no traen el dato", () => {
    expect(perdidasDeclaradas(128, [])).toBe("Pérdidas declaradas de los aparatos: 128 W");
    expect(perdidasDeclaradas(128, ["-S1"])).toBe("Pérdidas declaradas de los aparatos: 128 W (1 aparato no trae el dato)");
    expect(perdidasDeclaradas(1280, ["-S1", "-S2"])).toContain("1 280 W (2 aparatos no traen el dato)");
  });
});

describe("la vista del panel", () => {
  const props = { conductor: null, onConductor: () => {}, onEncuadrar: () => {} };
  const puerta = { valor: 0, min: 0, max: 110, onCambio: () => {}, onAnimar: () => {} };

  it("arriba el veredicto, los ítems como botones, la puerta y el detalle plegado", () => {
    const html = renderToStaticMarkup(h(VistaTablero, { ...props, panel: PANEL_CON_FALLAS, puerta }));
    expect(html).toContain("1 cosa por corregir y 4 por revisar");
    expect(html).toContain("Caja de 500 × 400 mm");
    expect(html.match(/class="ia-fila"/g)).toHaveLength(PANEL_CON_FALLAS.items.length);
    expect(html).toContain("112 %");
    expect(html).toContain(">Abrir<");
    expect(html).toMatch(/<details class="tb-plegable"><summary>Detalle<\/summary><\/details>/); // nace plegado
    expect(html.indexOf("vd-frase")).toBeLessThan(html.indexOf("items-atencion"));
    expect(html.indexOf("items-atencion")).toBeLessThan(html.indexOf("tb-puerta"));
  });

  it("un tablero que no se pudo armar: el veredicto, qué hacer y el motivo plegado; sin puerta ni detalle", () => {
    const html = renderToStaticMarkup(h(VistaTablero, { ...props, panel: PANEL_SIN_ARMAR, puerta }));
    expect(html).toContain("No se pudo armar el tablero");
    expect(html).toContain("Detalle técnico");
    expect(html).not.toContain("ia-fila");
    expect(html).not.toContain("tb-puerta");
    expect(html).not.toContain("tb-plegable");
  });

  it("sin tablero, el estado vacío dice qué va a aparecer y cómo pedirlo", () => {
    const html = renderToStaticMarkup(h(VacioTablero));
    expect(html).toContain("Aquí vas a ver el tablero armado");
    expect(html).toContain("Copiar el pedido");
  });
});
