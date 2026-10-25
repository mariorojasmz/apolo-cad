import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { EXTENSION_PRUEBA } from "../diseno/muestrario/extensionPrueba";
import { EXTENSIONES } from "../extensiones/registro";
import { chipsDe } from "../extensiones/puntosVivo";
import type { Extension } from "../extensiones/tipos";
import BarraVivo from "./BarraVivo";
import { INICIAL, useVivo } from "./estado";
import type { InicioVivo } from "./protocolo";

/* Los chips de las extensiones en la barra de la sesión viva (plan plc-en-el-lazo, D13 a): sin
   extensiones la barra es IDÉNTICA; con un chip, sólo se suma su contenedor tras el factor. */

const inicio = { dispositivos: [{ designacion: "-K1", tipo: "plc", ref: "PLC" }] } as unknown as InicioVivo;
const barra = (extensiones?: readonly Extension[]) =>
  renderToStaticMarkup(createElement(BarraVivo, extensiones ? { extensiones } : {}));

/* `renderToStaticMarkup` lee de zustand el estado INICIAL (el del servidor): la sesión de ejemplo
   se pone ahí y se devuelve al terminar. */
const inicial = useVivo.getInitialState();
const antes = { ...inicial };
const sesion = (p: Partial<typeof inicial>) => Object.assign(inicial, p);
afterAll(() => { Object.assign(inicial, antes); });

describe("chips de la barra viva", () => {
  beforeEach(() => {
    sesion({ ...INICIAL, fase: "corriendo", t: 12.4, factor: 1, inicio, lecturas: { "-K1.Main.consigna": 50 } });
  });

  it("sin chips la barra es la misma que sin extensiones (en el núcleo, la de siempre)", () => {
    const base = barra([]);
    expect(base).not.toContain("bv-chip");
    if (!chipsDe(EXTENSIONES).length) expect(barra()).toBe(base); // el núcleo no compila ninguna
    expect(base).toBe(barra([{ nombre: "vacia" }, { nombre: "solo-paneles", paneles: [] }]));
  });

  it("un chip entra justo tras el factor y no cambia nada más", () => {
    const base = barra([]);
    const con = barra([EXTENSION_PRUEBA]);
    const chip = '<span class="bv-chip" data-chip="prueba.consigna"><span aria-label="Consigna de la pantalla de prueba">Consigna 50 %</span></span>';
    expect(con).toContain(chip);
    expect(con.replace(chip, "")).toBe(base);
    const factor = con.indexOf('class="bv-factor');
    expect(factor).toBeGreaterThan(con.indexOf('class="bv-fase'));
    expect(con.indexOf(chip)).toBeGreaterThan(factor);
  });

  it("el chip de prueba sólo aparece con la sesión corriendo o en pausa", () => {
    sesion({ fase: "fin" });
    expect(barra([EXTENSION_PRUEBA])).toContain('data-chip="prueba.consigna"></span>');
  });
});
