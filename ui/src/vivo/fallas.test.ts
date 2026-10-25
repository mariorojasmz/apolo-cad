import { describe, expect, it } from "vitest";
import {
  activaIgual, activasDe, armarFalla, camposDe, conAckDeRama, elegidoInicial, nombreTipoFalla, objetivosDe,
  resumenActivas, rotuloFalla, valorDe, type EventoFalla, type Objetivo,
} from "./fallas";
import type { InicioVivo } from "./protocolo";

/* «Simular falla» (plan cosim-fallas D7): la lista sale del `inicio` (forma de
   `cosim/fallas.py::catalogo`), el evento tiene la forma que valida `cosim/escenario.py::_falla`
   y las activas se leen de `<des>.averia` (etiquetas de `Modelo.averia`) y de los acks de rama. */

const INICIO: Pick<InicioVivo, "fallas" | "ramas"> = {
  fallas: [
    { designacion: "-K1", tipo: "contactor", fallas: [{ falla: "soldado", pide: "" }, { falla: "no_cierra", pide: "" }] },
    { designacion: "-S0", tipo: "seta", fallas: [{ falla: "trabado", pide: "bool?" }] },
    { designacion: "-S5", tipo: "selector", fallas: [{ falla: "trabado", pide: "posicion?", opciones: ["0", "I", "II"] }] },
    { designacion: "-B1", tipo: "sensor", fallas: [{ falla: "pegado", pide: "bool" }, { falla: "sin_salida", pide: "" }] },
    { designacion: "-A1", tipo: "plc", fallas: [
      { falla: "entrada_pegada", pide: "borne,valor", opciones: ["I0.0", "I0.1", "AI0"] },
      { falla: "salida_pegada", pide: "borne,valor", opciones: ["Q0.0"] },
      { falla: "detenido", pide: "" }] },
    { designacion: "-T1", tipo: "variador", fallas: [
      { falla: "canal_sto_pegado", pide: "canal", opciones: ["S1", "S2"] }, { falla: "falla_interna", pide: "" }] },
    { designacion: "-F2", tipo: "fusible", fallas: [{ falla: "no_dispara", pide: "" }, { falla: "abierto", pide: "unidad?", opciones: [1, 2, 3] }] },
    { designacion: "-B2", tipo: "resguardo", fallas: [{ falla: "trabado", pide: "bool?" }] },
    { designacion: "-K2", tipo: "rele_seguridad", fallas: [
      { falla: "salida_pegada", pide: "salida", opciones: ["13-14", "23-24", "33-34"] }, { falla: "detenido", pide: "" }] },
  ],
  ramas: [
    { id: "-K1:13-14", tipo: "contacto", red: "mando", dispositivo: "-K1" },
    { id: "-W3", tipo: "conductor", red: "potencia" },
  ],
};

const objetivos = objetivosDe(INICIO);
const de = (clave: string): Objetivo => objetivos.find((o) => o.clave === clave)!;
const falla = (o: Objetivo, n: string) => o.fallas.find((f) => f.falla === n)!;

describe("objetivosDe", () => {
  it("aparatos y ramas en el orden del inicio; un contacto se pega o se abre, un cable sólo se corta", () => {
    expect(objetivos.map((o) => o.clave)).toEqual(["d:-K1", "d:-S0", "d:-S5", "d:-B1", "d:-A1", "d:-T1", "d:-F2", "d:-B2", "d:-K2", "r:-K1:13-14", "r:-W3"]);
    expect(de("r:-K1:13-14").fallas.map((f) => f.falla)).toEqual(["pegado", "abierto"]);
    expect(de("r:-W3").fallas.map((f) => f.falla)).toEqual(["abierto"]);
  });

  it("un servidor anterior (sin fallas ni ramas) no ofrece nada", () => {
    expect(objetivosDe({})).toEqual([]);
  });
});

describe("rótulos", () => {
  it("cada falla del contrato tiene rótulo para la persona; una desconocida, su nombre legible", () => {
    expect(rotuloFalla(de("d:-K1"), "soldado")).toBe("Contacto soldado");
    expect(rotuloFalla(de("d:-F2"), "abierto")).toBe("Fundido");
    expect(rotuloFalla(de("r:-W3"), "abierto")).toBe("Cable cortado");
    expect(rotuloFalla(de("d:-K1"), "bobina_quemada")).toBe("Bobina quemada");
  });
});

describe("el evento", () => {
  it("una falla sin valor: dispositivo y falla, nada más", () => {
    expect(armarFalla(de("d:-K1"), falla(de("d:-K1"), "soldado"))).toEqual({ tipo: "falla", dispositivo: "-K1", falla: "soldado" });
  });

  it("valor opcional: «como está ahora» no lo manda; elegido, sí", () => {
    const seta = de("d:-S0");
    const f = falla(seta, "trabado");
    expect(camposDe(seta, f)[0].tipo).toBe("lista");
    expect(armarFalla(seta, f)).toEqual({ tipo: "falla", dispositivo: "-S0", falla: "trabado" });
    expect(armarFalla(seta, f, { valor: "1" }).valor).toBe(true);
    const sel = de("d:-S5");
    expect(armarFalla(sel, falla(sel, "trabado"), { valor: "II" }).valor).toBe("II");
  });

  it("el sensor pegado pide cómo queda (por defecto, detectando)", () => {
    const b = de("d:-B1");
    expect(valorDe(b, falla(b, "pegado"), {})).toBe(true);
    expect(valorDe(b, falla(b, "pegado"), { valor: "0" })).toBe(false);
  });

  it("borne y valor del PLC: digital con nivel, analógica con su cuenta", () => {
    const plc = de("d:-A1");
    const f = falla(plc, "entrada_pegada");
    expect(camposDe(plc, f).map((c) => c.id)).toEqual(["borne", "valor"]);
    expect(armarFalla(plc, f).valor).toEqual({ borne: "I0.0", valor: true });
    expect(armarFalla(plc, f, { borne: "I0.1", valor: "0" }).valor).toEqual({ borne: "I0.1", valor: false });
    expect(camposDe(plc, f, { borne: "AI0" }).map((c) => c.id)).toEqual(["borne", "cuenta"]);
    expect(armarFalla(plc, f, { borne: "AI0", cuenta: "13824.4" }).valor).toEqual({ borne: "AI0", valor: 13824 });
  });

  it("el canal del STO es obligatorio; la unidad del fusible, opcional (todas)", () => {
    const t1 = de("d:-T1");
    expect(armarFalla(t1, falla(t1, "canal_sto_pegado")).valor).toBe("S1");
    const f2 = de("d:-F2");
    expect(elegidoInicial(f2, falla(f2, "abierto"))).toEqual({ valor: "" });
    expect(armarFalla(f2, falla(f2, "abierto")).valor).toBeUndefined();
    expect(armarFalla(f2, falla(f2, "abierto"), { valor: "2" }).valor).toBe(2);
  });

  it("relé de seguridad: la salida soldada pide cuál, de las que publica el inicio (mandos-de-seguridad D3)", () => {
    const k2 = de("d:-K2");
    const f = falla(k2, "salida_pegada");
    const [campo] = camposDe(k2, f);
    expect(campo).toMatchObject({ id: "valor", rotulo: "Salida", tipo: "lista" });
    expect(campo.tipo === "lista" && campo.opciones).toEqual([
      { clave: "13-14", rotulo: "Bornes 13-14" }, { clave: "23-24", rotulo: "Bornes 23-24" }, { clave: "33-34", rotulo: "Bornes 33-34" }]);
    // la forma que acepta `ReleSeguridad._salida`: el texto de los bornes, nunca sin valor
    expect(armarFalla(k2, f)).toEqual({ tipo: "falla", dispositivo: "-K2", falla: "salida_pegada", valor: "13-14" });
    expect(armarFalla(k2, f, { valor: "23-24" }).valor).toBe("23-24");
    expect(rotuloFalla(k2, "salida_pegada")).toBe("Salida de seguridad soldada");
    expect(armarFalla(k2, falla(k2, "detenido"))).toEqual({ tipo: "falla", dispositivo: "-K2", falla: "detenido" });
  });

  it("resguardo trabado: los contactos quedan como están, cerrados o abiertos", () => {
    const b2 = de("d:-B2");
    const [campo] = camposDe(b2, falla(b2, "trabado"));
    expect(campo.tipo === "lista" && campo.opciones.map((o) => o.rotulo)).toEqual(["Como está ahora", "Contactos cerrados", "Contactos abiertos"]);
    expect(armarFalla(b2, falla(b2, "trabado"), { valor: "0" }).valor).toBe(false);
  });

  it("rama: el contacto pegado lleva cerrado (true) o abierto (false); el cable cortado, nada", () => {
    const k = de("r:-K1:13-14");
    expect(armarFalla(k, falla(k, "pegado"))).toEqual({ tipo: "falla", rama: "-K1:13-14", falla: "pegado", valor: true });
    expect(armarFalla(k, falla(k, "pegado"), { valor: "0" }).valor).toBe(false);
    expect(armarFalla(de("r:-W3"), falla(de("r:-W3"), "abierto"))).toEqual({ tipo: "falla", rama: "-W3", falla: "abierto" });
  });
});

describe("las activas", () => {
  it("lee las etiquetas de `averia` con su argumento y arma el quitar que identifica a cada una", () => {
    const a = activasDe({
      "-K1.averia": "soldado", "-A1.averia": "entrada_pegada I0.0, salida_pegada Q0.0", "-T1.averia": "",
      "-F2.averia": "abierto 2", "-T1.estado": "listo",
    }, INICIO);
    expect(a.map((x) => x.frase)).toEqual([
      "contacto soldado en -K1", "entrada I0.0 pegada en -A1", "salida Q0.0 pegada en -A1", "fusible 2 fundido en -F2",
    ]);
    expect(a[1].quitar).toEqual({ tipo: "falla", dispositivo: "-A1", falla: "entrada_pegada", valor: { borne: "I0.0" }, quitar: true });
    expect(a[3].quitar.valor).toBe(2);
    expect(a[0].quitar).toEqual({ tipo: "falla", dispositivo: "-K1", falla: "soldado", quitar: true });
  });

  it("la salida soldada del relé se quita con su salida, no con un borne del PLC", () => {
    const a = activasDe({ "-K2.averia": "salida_pegada 13-14, detenido" }, INICIO);
    expect(a.map((x) => x.frase)).toEqual(["salida de seguridad 13-14 soldada en -K2", "relé detenido en -K2"]);
    expect(a[0].quitar).toEqual({ tipo: "falla", dispositivo: "-K2", falla: "salida_pegada", valor: "13-14", quitar: true });
    const k2 = de("d:-K2");
    const f = falla(k2, "salida_pegada");
    expect(activaIgual(a, armarFalla(k2, f))?.clave).toBe("-K2|salida_pegada 13-14");
    expect(activaIgual(a, armarFalla(k2, f, { valor: "23-24" }))).toBeUndefined();
  });

  it("la barra dice la falla con una y la cuenta con varias", () => {
    expect(resumenActivas([])).toBe("");
    expect(resumenActivas(activasDe({ "-K1.averia": "soldado" }, INICIO))).toBe("Falla activa: contacto soldado en -K1");
    expect(resumenActivas(activasDe({ "-K1.averia": "soldado", "-S0.averia": "trabado" }, INICIO))).toBe("2 fallas activas");
  });

  it("las de rama se llevan por el ack: ponerla la suma, quitarla la saca, otro ack no cambia nada", () => {
    let ramas: readonly EventoFalla[] = [];
    ramas = conAckDeRama(ramas, { tipo: "falla", rama: "-K1:13-14", falla: "pegado", valor: false });
    ramas = conAckDeRama(ramas, { tipo: "falla", rama: "-W3", falla: "abierto" });
    const igual = conAckDeRama(ramas, { tipo: "atasco", junta: "j1" });
    expect(igual).toBe(ramas);
    expect(conAckDeRama(ramas, undefined)).toBe(ramas);
    expect(activasDe({}, INICIO, ramas).map((x) => x.frase)).toEqual([
      "contacto pegado abierto en -K1:13-14", "cable cortado en -W3",
    ]);
    ramas = conAckDeRama(ramas, { tipo: "falla", rama: "-W3", falla: "abierto", quitar: true });
    expect(ramas).toEqual([{ tipo: "falla", rama: "-K1:13-14", falla: "pegado", valor: false }]);
  });

  it("el botón ofrece quitar sólo la misma falla (con el mismo borne, canal o unidad)", () => {
    const activas = activasDe({ "-A1.averia": "entrada_pegada I0.0", "-K1.averia": "soldado" }, INICIO);
    const plc = de("d:-A1");
    const f = falla(plc, "entrada_pegada");
    expect(activaIgual(activas, armarFalla(plc, f, { borne: "I0.0", valor: "0" }))?.clave).toBe("-A1|entrada_pegada I0.0");
    expect(activaIgual(activas, armarFalla(plc, f, { borne: "I0.1" }))).toBeUndefined();
    expect(activaIgual(activas, armarFalla(de("d:-K1"), falla(de("d:-K1"), "soldado")))).toBeDefined();
    expect(activaIgual(activas, armarFalla(de("d:-K1"), falla(de("d:-K1"), "no_cierra")))).toBeUndefined();
  });
});

describe("el diferencial (plan datos-de-corte-y-acometida D8)", () => {
  it("tiene nombre de tipo y sus fallas se dicen como las de una protección", () => {
    expect(nombreTipoFalla("diferencial")).toBe("Interruptor diferencial");
    const inicio: Pick<InicioVivo, "fallas" | "ramas"> = {
      fallas: [{ designacion: "-F1", tipo: "diferencial", fallas: [{ falla: "no_dispara", pide: "" }, { falla: "abierto", pide: "" }] }],
      ramas: [],
    };
    const [a, b] = activasDe({ "-F1.averia": "abierto, no_dispara" }, inicio);
    expect(a.frase).toBe("protección disparada sola en -F1");
    expect(b.frase).toBe("protección que no dispara en -F1");
  });
});

describe("el panel de operador (plc-en-el-lazo D12)", () => {
  const ini: Pick<InicioVivo, "fallas" | "ramas"> = {
    fallas: [{ designacion: "-P2", tipo: "hmi", fallas: [{ falla: "apagada", pide: "" }] }],
  };
  const panel = objetivosDe(ini)[0];

  it("tiene nombre de tipo y de falla; no pide valor", () => {
    expect(nombreTipoFalla("hmi")).toBe("Panel de operador");
    expect(rotuloFalla(panel, "apagada")).toBe("Pantalla apagada");
    expect(camposDe(panel, panel.fallas[0])).toEqual([]);
    expect(armarFalla(panel, panel.fallas[0])).toEqual({ tipo: "falla", dispositivo: "-P2", falla: "apagada" });
  });

  it("la activa se lee de su `averia` y se quita con su evento", () => {
    const [a] = activasDe({ "-P2.averia": "apagada" }, ini);
    expect(a.frase).toBe("pantalla apagada en -P2");
    expect(a.quitar).toEqual({ tipo: "falla", dispositivo: "-P2", falla: "apagada", quitar: true });
  });
});
