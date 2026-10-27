import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { INICIO_DEMO } from "../diseno/muestrario/datosVivo";
import { INICIAL, useVivo } from "./estado";
import { CabezaAparato, FilaMando } from "./FilaMando";
import {
  designacionSecundaria, estadoJuntoAlBoton, gruposDeMandos, muestraColorFisico, nombrePrincipal, segmentoLeido, segmentosDe,
  veredictoMandos, type Leidas,
} from "./nombresMandos";
import { ListaMandos } from "./PanelMandos";
import type { InicioVivo, MandoVivo } from "./protocolo";
import Segmentado from "./Segmentado";

/* «Mandos» por función (plan nombres-por-funcion D9–D12) sobre la mezcladora del muestrario:
   el rótulo manda y la designación va detrás; un mando que se queda marca el estado LEÍDO de su
   señal; el rearme dice cómo están sus relés; el veredicto sólo dice hechos leídos. */

const mando = (des: string): MandoVivo => INICIO_DEMO.mandos.find((m) => m.designacion === des)!;
const leidas = (valores: Record<string, number>, textos: Record<string, string> = {}): Leidas => ({
  valor: (s) => valores[s],
  texto: (s) => textos[s],
});

describe("el nombre de la fila", () => {
  it("el rótulo es lo principal y la designación va detrás; sin rótulo (servidor anterior), la designación sola", () => {
    expect(nombrePrincipal(mando("-S3"))).toBe("Rearme de seguridad");
    expect(designacionSecundaria(mando("-S3"))).toBe("-S3");
    const viejo = { ...mando("-S3"), rotulo: undefined };
    expect(nombrePrincipal(viejo)).toBe("-S3");
    expect(designacionSecundaria(viejo)).toBeNull();
  });

  it("en pantalla, el rótulo con su peso va primero y la designación chica después; la descripción, sólo en la ⓘ", () => {
    const html = renderToStaticMarkup(createElement(CabezaAparato, { a: mando("-S2") }));
    expect(html.indexOf('class="rotulo-aparato">Paro<')).toBeGreaterThanOrEqual(0);
    // la pieza es la de todas las superficies (`diseno/NombreAparato.tsx`, F4): la designación no se corta
    expect(html.indexOf('class="designacion-aparato"><span class="designacion-codigo">-S2<'))
      .toBeGreaterThan(html.indexOf("rotulo-aparato"));
    expect(html).toContain('aria-label="Ayuda sobre «Paro»"');
    expect(html).not.toContain("No corta la energía"); // cerrada hasta que la piden
    expect(renderToStaticMarkup(createElement(CabezaAparato, { a: mando("-S1") }))).not.toContain("ayuda-btn");
  });
});

describe("grupos (D11)", () => {
  it("con más de 5 mandos: Energía, Seguridad y Operación, del grupo del servidor", () => {
    const g = gruposDeMandos(INICIO_DEMO.mandos);
    expect(g.map((x) => x.titulo)).toEqual(["Energía", "Seguridad", "Operación"]);
    expect(g.map((x) => x.mandos.map((m) => m.designacion))).toEqual([["-Q1"], ["-S0", "-S3", "-B1", "-B4"], ["-S1", "-S2", "-S4"]]);
  });

  it("con 5 o menos, o sin grupos (servidor anterior), una sola lista «Mandos»", () => {
    expect(gruposDeMandos(INICIO_DEMO.mandos.slice(0, 5)).map((x) => x.titulo)).toEqual(["Mandos"]);
    expect(gruposDeMandos(INICIO_DEMO.mandos.map((m) => ({ ...m, grupo: undefined }))).map((x) => x.titulo)).toEqual(["Mandos"]);
  });
});

describe("mandos que se quedan: segmentados (D9, A18)", () => {
  it("los segmentos son los estados con nombre, en el orden del servidor", () => {
    expect(segmentosDe(mando("-Q1"))).toEqual([{ clave: "cerrado", rotulo: "Encendido" }, { clave: "abierto", rotulo: "Apagado" }]);
    expect(segmentosDe(mando("-B4"))!.map((s) => s.rotulo)).toEqual(["Acoplado", "Sin recipiente"]);
    expect(segmentosDe(mando("-S4"))).toEqual([{ clave: "0", rotulo: "Manual" }, { clave: "I", rotulo: "Ciclo" }]);
    expect(segmentosDe(mando("-S1"))).toBeNull(); // el pulsador sigue siendo botón
    expect(segmentosDe(mando("-S0"))).toBeNull(); // y la seta
    expect(segmentosDe({ ...mando("-B1"), estados: undefined })).toBeNull(); // servidor anterior: el botón de siempre
  });

  it("el segmento marcado es el LEÍDO de la señal: bool para el resguardo, texto para el selector", () => {
    expect(segmentoLeido(mando("-B1"), leidas({ "-B1.cerrado": 0 }))).toBe("abierto");
    expect(segmentoLeido(mando("-Q1"), leidas({ "-Q1.cerrado": 1 }))).toBe("cerrado");
    expect(segmentoLeido(mando("-S4"), leidas({}, { "-S4.posicion": "I" }))).toBe("I");
    expect(segmentoLeido(mando("-S4"), leidas({}))).toBeUndefined(); // todavía sin señal: ninguno
  });

  it("el control marca el valor que recibe, sin guardar estado propio", () => {
    const html = (valor: string | undefined) => renderToStaticMarkup(createElement(Segmentado, {
      etiqueta: "Modo", segmentos: segmentosDe(mando("-S4"))!, valor, quieto: false, alElegir: () => {},
    }));
    expect(html("I")).toMatch(/aria-pressed="false"[^>]*>Manual<\/button><button[^>]*aria-pressed="true" class="marcado"[^>]*>Ciclo</);
    expect(html(undefined)).not.toContain('aria-pressed="true"');
    expect(html("I")).not.toContain("disabled"); // nada se deshabilita por no tener efecto (D10)
  });
});

describe("al lado del botón (D10)", () => {
  it("el rearme dice cómo están los relés que rearma; la seta, si está presionada", () => {
    const s3 = mando("-S3");
    expect(estadoJuntoAlBoton(s3, leidas({ "-K2.salidas": 0, "-K3.salidas": 1 }))).toBe("Falta rearmar");
    expect(estadoJuntoAlBoton(s3, leidas({ "-K2.salidas": 1, "-K3.salidas": 1 }))).toBe("Rearmada");
    expect(estadoJuntoAlBoton(s3, leidas({ "-K2.salidas": 1 }))).toBeNull(); // falta una lectura: no se afirma
    expect(estadoJuntoAlBoton(mando("-S0"), leidas({ "-S0.accionado": 1 }))).toBe("Presionada");
    expect(estadoJuntoAlBoton(mando("-S1"), leidas({ "-S1.accionado": 1 }))).toBeNull();
  });
});

describe("el veredicto (D12)", () => {
  const ini = INICIO_DEMO;
  const base = { "-Q1.cerrado": 1, "-S0.accionado": 0, "-B1.cerrado": 1, "-B4.cerrado": 1, "-K2.salidas": 1, "-K3.salidas": 1 };

  it("el título es la causa leída y la nota, la acción siguiente de los mismos hechos (F5b)", () => {
    expect(veredictoMandos(ini, leidas({ ...base, "-Q1.cerrado": 0, "-S0.accionado": 1 }))).toEqual({
      severidad: "aviso", frase: "Sin energía", nota: "Enciende el interruptor general", paso: { designacion: "-Q1", clave: "cerrado" } });
    expect(veredictoMandos(ini, leidas({ ...base, "-S0.accionado": 1, "-K2.salidas": 0 }))).toEqual({
      severidad: "aviso", frase: "Parada de emergencia presionada", nota: "Libera la parada de emergencia", paso: { designacion: "-S0" } });
    expect(veredictoMandos(ini, leidas({ ...base, "-B1.cerrado": 0, "-K2.salidas": 0 }))).toEqual({
      severidad: "aviso", frase: "Tapa del tanque abierta", nota: "Cierra la tapa del tanque", paso: { designacion: "-B1", clave: "cerrado" } });
    // un estado declarado que no es «cerrado»: la acción lo dice con su nombre
    expect(veredictoMandos(ini, leidas({ ...base, "-B4.cerrado": 0 }))).toMatchObject({
      frase: "Recipiente bajo la descarga: sin recipiente", nota: "Pon el recipiente bajo la descarga en «Acoplado»" });
  });

  it("sin nada que bloquee: energía y seguridad habilitadas, nunca «lista para arrancar»", () => {
    expect(veredictoMandos(ini, leidas(base))).toEqual({ severidad: "bien", frase: "Energía y seguridad habilitadas" });
    expect(veredictoMandos(ini, leidas({}))).toBeNull(); // nada leído todavía
  });

  it("un relé que corta: «Seguridad sin rearmar» y «Rearma la seguridad», con el rearme como paso; nunca un relé con un verbo", () => {
    for (const salidas of [{ "-K2.salidas": 0, "-K3.salidas": 0 }, { "-K3.salidas": 0 }]) {
      expect(veredictoMandos(ini, leidas({ ...base, ...salidas }))).toEqual({
        severidad: "aviso", frase: "Seguridad sin rearmar", nota: "Rearma la seguridad", paso: { designacion: "-S3" } });
    }
    const sinRearme: Pick<InicioVivo, "mandos" | "dispositivos"> = { mandos: [], dispositivos: ini.dispositivos };
    expect(veredictoMandos(sinRearme, leidas({ "-K2.salidas": 0 }))!.paso).toBeUndefined();
    const textos = [base, { ...base, "-K3.salidas": 0 }, { ...base, "-Q1.cerrado": 0 }, { ...base, "-B1.cerrado": 0 }]
      .map((l) => veredictoMandos(ini, leidas(l))!).flatMap((v) => [v.frase, v.nota ?? ""]);
    for (const t of textos) {
      expect(t).not.toMatch(/corta la marcha|Lista para arrancar|lista para arrancar/);
      expect(t).not.toContain("Seguridad de"); // el nombre de un relé, nunca con un verbo pegado
    }
  });
});

describe("el próximo paso y el estado de lo que se queda (F5b)", () => {
  const html = (des: string, paso?: { designacion: string; clave?: string }) =>
    renderToStaticMarkup(createElement(FilaMando, { m: mando(des), quieto: false, paso }));

  it("el control que pide el veredicto va con el estilo primario del tema; ningún otro, y nada deshabilitado", () => {
    expect(html("-S0", { designacion: "-S0" })).toMatch(/class="boton-mando[^"]* primary"/);
    expect(html("-S0")).not.toContain("primary");
    expect(html("-S3", { designacion: "-S3" })).toMatch(/class="boton-mando[^"]* primary"[^>]*>Presionar</);
    // el segmento a elegir, sin tocar el marcado
    const seg = renderToStaticMarkup(createElement(Segmentado, {
      etiqueta: "Tapa", segmentos: segmentosDe(mando("-B1"))!, valor: "abierto", quieto: false, primario: "cerrado", alElegir: () => {} }));
    expect(seg).toMatch(/class="primary"[^>]*>Cerrada</);
    expect(seg).toMatch(/class="marcado"[^>]*>Abierta</);
    expect(seg.match(/primary/g)).toHaveLength(1);
    expect(seg).not.toContain("disabled");
  });

  it("el segmento no elegido no se ve deshabilitado: tinta plena; el elegido gana contraste", async () => {
    const { readFileSync } = await import("node:fs");
    const css = readFileSync(new URL("./mandos.css", import.meta.url), "utf8");
    const regla = (sel: string) => new RegExp(`${sel.replace(/[.()]/g, "\\$&")}\\s*\\{([^}]*)\\}`).exec(css)?.[1] ?? "";
    expect(regla(".segmentado button:not(.primary)")).toContain("color: var(--text)");
    expect(css).not.toMatch(/\.segmentado button[^{]*\{[^}]*(--muted|opacity)/);
    expect(regla(".segmentado button.marcado")).toMatch(/background: var\(--panel3\)/);
    expect(regla(".segmentado button.marcado")).toMatch(/var\(--accent\)/);
  });

  it("el cuadrado del color físico sólo donde el color informa: pulsador y seta, no seccionador, resguardo ni selector", () => {
    expect(INICIO_DEMO.mandos.filter(muestraColorFisico).map((m) => m.designacion)).toEqual(["-S0", "-S1", "-S2", "-S3"]);
    for (const des of ["-Q1", "-B1", "-B4", "-S4"]) expect(html(des)).not.toContain("tapa-mando");
    for (const des of ["-S0", "-S1"]) expect(html(des)).toContain("tapa-mando");
  });
});

describe("el panel con la sesión de la mezcladora", () => {
  /* `renderToStaticMarkup` lee de zustand el estado INICIAL: la sesión se pone ahí (chips.test.ts). */
  const inicial = useVivo.getInitialState();
  const antes = { ...inicial };
  afterAll(() => { Object.assign(inicial, antes); });
  beforeEach(() => {
    Object.assign(inicial, { ...INICIAL, fase: "corriendo", inicio: INICIO_DEMO, textos: { "-S4.posicion": "0" },
      lecturas: { "-Q1.cerrado": 1, "-S0.accionado": 0, "-B1.cerrado": 0, "-B4.cerrado": 1, "-K2.salidas": 0, "-K3.salidas": 1 } });
  });

  it("el veredicto arriba, una sola pista del 3D y la fila con el rótulo primero", () => {
    const html = renderToStaticMarkup(createElement(ListaMandos, { quieto: false }));
    expect(html.indexOf("Tapa del tanque abierta")).toBeLessThan(html.indexOf("<h3>Energía</h3>"));
    expect(html.match(/clic en el 3D/g)).toHaveLength(1);
    expect(html).not.toMatch(/Pulsador|Seccionador|Resguardo/); // ningún nombre de tipo inventado
  });

  it("el resguardo marca «Abierta» y el selector «Manual», leídos de sus señales", () => {
    const fila = (des: string) => renderToStaticMarkup(createElement(FilaMando, { m: mando(des), quieto: false }));
    expect(fila("-B1")).toMatch(/aria-pressed="true" class="marcado"[^>]*>Abierta</);
    expect(fila("-S4")).toMatch(/aria-pressed="true" class="marcado"[^>]*>Manual</);
    expect(fila("-S3")).toContain('class="estado-mando" aria-live="polite">Falta rearmar<');
  });
});
