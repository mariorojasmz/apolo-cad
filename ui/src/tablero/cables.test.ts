import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import DetalleTablero from "./DetalleTablero";
import { PANEL_CON_FALLAS, PANEL_EN_ORDEN } from "../diseno/muestrario/datosTablero";
import { radioDelRecorrido } from "./recorrido3d";
import type { CableTablero, PanelTableroOut } from "./tipos";
import { alElegir, cablesListados, largoCable, partesCable, recorridoDe, supuestosDe } from "./vista";

/* Los cables de campo en el panel «Tablero» (plan V8.5 F4b): se dibujan como un conductor (mismo
   espacio de ids), el ítem del choque los encuadra enteros, el detalle dice de qué sale su largo y
   el tubo se sigue viendo fino aunque el recorrido mida metros. Datos: los del muestrario. */

function acciones() {
  return { encuadrar: vi.fn(), elegir: vi.fn(), dibujar: vi.fn() };
}

const cable = (p: Partial<CableTablero>): CableTablero =>
  ({ id: "c9", designacion: "-W9", ref: "CABLE-5G1", calculado: true, piezas: [], ...p });

describe("cables de campo en el panel Tablero", () => {
  it("el recorrido de un cable se encuentra como el de un conductor", () => {
    const w2 = PANEL_CON_FALLAS.detalle!.cables![1];
    expect(recorridoDe(PANEL_CON_FALLAS, w2.id)).toBe(w2.recorrido);
    expect(recorridoDe(PANEL_CON_FALLAS, "c26")).toBe(PANEL_CON_FALLAS.detalle!.conductores[0].recorrido);
    const sinCables: PanelTableroOut = { ...PANEL_EN_ORDEN, detalle: { ...PANEL_EN_ORDEN.detalle!, cables: undefined } };
    expect(recorridoDe(sinCables, w2.id)).toBeNull();
  });

  it("el ítem del cable que roza lo que gira lo dibuja y encuadra su recorrido entero con el tambor", () => {
    const it = PANEL_CON_FALLAS.items.find((x) => x.clave.startsWith("cable-giro-"))!;
    const a = acciones();
    alElegir(it, a, PANEL_CON_FALLAS);
    expect(a.dibujar).toHaveBeenCalledWith("c20");
    const [piezas, puntos] = a.encuadrar.mock.calls[0];
    expect(piezas).toEqual(["tambor"]);
    expect(puntos).toEqual(PANEL_CON_FALLAS.detalle!.cables![1].recorrido![0]);
  });

  it("la fila dice de qué sale el largo, el puesto a mano y lo incompleto", () => {
    const w1 = PANEL_CON_FALLAS.detalle!.cables![0];
    expect(largoCable(w1)).toMatch(/^\d,\d\d m$/);
    expect(partesCable(cable({ largo_m: 4.57, partes_m: { adentro: 0.379, afuera: 3.89, reserva: 0.3 } })))
      .toBe("Dentro 0,38 m · afuera 3,89 m · reserva 0,30 m");
    expect(partesCable(cable({ partes_m: { adentro: 0, afuera: 1, reserva: 0 }, declarado_m: 6, incompleto: true })))
      .toBe("Recorrido incompleto · Dentro 0,00 m · afuera 1,00 m · reserva 0,00 m · Puesto a mano: 6,00 m");
    expect(largoCable(cable({ calculado: false, incompleto: true }))).toBeUndefined();
    // el largo del ejemplo es la suma de sus partes
    const p = w1.partes_m!;
    expect(p.adentro + p.afuera + p.reserva).toBeCloseTo(w1.largo_m!, 2);
  });

  it("el filtro de un ítem lista sus cables y los supuestos llevan la designación", () => {
    expect(cablesListados(PANEL_CON_FALLAS, ["c20"]).map((c) => c.id)).toEqual(["c20"]);
    expect(cablesListados(PANEL_CON_FALLAS, null)).toHaveLength(2);
    const p: PanelTableroOut = { ...PANEL_EN_ORDEN, detalle: { ...PANEL_EN_ORDEN.detalle!,
      cables: [cable({ supuestos: ["sale por la vertical más cercana", "-W9: ya nombrado"] })] } };
    expect(supuestosDe(p)).toEqual([...PANEL_EN_ORDEN.detalle!.supuestos, "-W9: sale por la vertical más cercana", "-W9: ya nombrado"]);
  });

  it("el detalle muestra la sección de cables sólo si hay; con un filtro de cables, sin conductores vacíos", () => {
    const a = acciones();
    const html = renderToStaticMarkup(h(DetalleTablero, { panel: PANEL_CON_FALLAS, acciones: a, conductor: null,
      filtro: null, quitarFiltro: () => {} }));
    expect(html).toContain("Cables de campo · 2");
    expect(html).toContain("Cable de sensor 3x0,75");
    const filtrado = renderToStaticMarkup(h(DetalleTablero, { panel: PANEL_CON_FALLAS, acciones: a, conductor: null,
      filtro: ["c19", "c20"], quitarFiltro: () => {} }));
    expect(filtrado).not.toContain("Conductores ·");
    const sin: PanelTableroOut = { ...PANEL_EN_ORDEN, detalle: { ...PANEL_EN_ORDEN.detalle!, cables: [] } };
    expect(renderToStaticMarkup(h(DetalleTablero, { panel: sin, acciones: a, conductor: null, filtro: null,
      quitarFiltro: () => {} }))).not.toContain("Cables de campo");
  });

  it("el tubo es fino en la pantalla: el mínimo dentro del tablero, más grueso en un recorrido de metros", () => {
    expect(radioDelRecorrido([[[0, 0, 0], [300, 0, 0]]])).toBe(1.6);
    expect(radioDelRecorrido([])).toBe(1.6);
    expect(radioDelRecorrido([[[0, 0, 0], [4000, 0, 0]]])).toBeCloseTo(6, 5);
  });
});
