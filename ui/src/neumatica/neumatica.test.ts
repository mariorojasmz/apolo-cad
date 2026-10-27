import { describe, expect, it } from "vitest";
import { Historia } from "../vivo/historia";
import { textosDelArbol, arbolDeSenales } from "../vivo/arbolSenales";
import { lecturasDe, textoLectura } from "../vivo/lecturas";
import { hayAtasco } from "../vivo/mandos";
import { leerValor, medidaDe } from "../vivo/unidades";
import { rotuloAire } from "./senales";
import { aireMedio, senalesDeAire, textoAire } from "./aire";
import { nombreEnLinea } from "../diseno/nombres";
import {
  altoTexto, AMPLIADO_PX_MM, colorPresion, conNombre, convieneAmpliar, detalleSimbolo, elegidosPor, escalaEsquema,
  MIN_PX_MM, MIN_TEXTO_PX, pasoDe, posicionDe, presionDe, RAMPA_PRESION, rotuloCilindro, SIN_PRESION, textoConsumo,
  textoFuerza, textoTiempo, topeLeyenda, type Lector,
} from "./esquema";
import {
  accionManual, alternarManual, ladosManual, manualPersona, nombrePosicion, posicionPersona, rotuloLado,
} from "./manual";
import type { PresionLinea, ValvulaEsquema } from "./tipos";

/* El panel «Neumática» (plan V8.9 D12): la presión de cada línea con las señales vivas, su color y
   su leyenda, la posición de cada válvula, la selección del 3D, las cifras del detalle, el aire de
   la barra, el accionamiento manual, la válvula en el árbol de Señales y la etiqueta del cilindro. */

function lector(num: Record<string, number>, texto: Record<string, string> = {}): Lector {
  return { num: (n) => num[n], texto: (n) => texto[n] };
}

describe("la presión de una línea", () => {
  const alim: PresionLinea = { senal: "-AZ1.p_bar", si: "-QM1.abierta" };
  const via: PresionLinea = { valvula: "-QM2", tabla: { "14": "1", "12": "5" }, alimentacion: alim };

  it("la de una cámara sale de su señal; un escape es 0", () => {
    expect(presionDe({ senal: "-MM1.pA_bar" }, lector({ "-MM1.pA_bar": 5.9 }))).toBe(5.9);
    expect(presionDe({ senal: "-MM1.pB_bar" }, lector({ "-MM1.pB_bar": -0.01 }))).toBe(0);
    expect(presionDe({ atmosfera: true }, lector({}))).toBe(0);
    expect(presionDe({}, lector({}))).toBeUndefined();
    expect(presionDe({ senal: "-MM1.pA_bar" }, lector({}))).toBeUndefined();
  });

  it("tras la válvula de corte, sólo si está abierta", () => {
    expect(presionDe(alim, lector({ "-AZ1.p_bar": 6, "-QM1.abierta": 1 }))).toBe(6);
    expect(presionDe(alim, lector({ "-AZ1.p_bar": 6, "-QM1.abierta": 0 }))).toBe(0);
  });

  it("una vía de trabajo sigue a la posición de su válvula", () => {
    const num = { "-AZ1.p_bar": 6, "-QM1.abierta": 1 };
    expect(presionDe(via, lector(num, { "-QM2.posicion": "14" }))).toBe(6);
    expect(presionDe(via, lector(num, { "-QM2.posicion": "12" }))).toBe(0);
    expect(presionDe(via, lector(num, {}))).toBeUndefined();
    expect(presionDe({ ...via, tabla: { "0": null } }, lector(num, { "-QM2.posicion": "0" }))).toBeUndefined();
  });
});

describe("la escala de la presión", () => {
  it("sin aire en gris neutro; con aire, cinco pasos de un solo tono hasta la regulada", () => {
    expect(RAMPA_PRESION).toHaveLength(5);
    expect(pasoDe(0, 6)).toBe(-2);
    expect(colorPresion(0.02, 6)).toBe(SIN_PRESION);
    expect(pasoDe(0.3, 6)).toBe(0);
    expect(pasoDe(6, 6)).toBe(4);
    expect(pasoDe(9, 6)).toBe(4);
    expect(pasoDe(3, 6)).toBe(2);
    expect(colorPresion(undefined, 6)).toBeNull();
    expect(colorPresion(6, 6)).toBe(RAMPA_PRESION[4]);
  });

  it("la leyenda dice su tope con unidad", () => {
    expect(topeLeyenda(6)).toBe("6 bar");
    expect(topeLeyenda(6.5)).toBe("6,5 bar");
  });
});

describe("el esquema", () => {
  const v52: ValvulaEsquema = { designacion: "-QM2", tipo: "valvula", senal: "-QM2.posicion", cajas: {} };
  const corte: ValvulaEsquema = { designacion: "-QM1", tipo: "valvula_corte", senal: "-QM1.abierta", cajas: {} };

  it("la posición de cada válvula, de su señal", () => {
    expect(posicionDe(v52, lector({}, { "-QM2.posicion": "14" }))).toBe("14");
    expect(posicionDe(corte, lector({ "-QM1.abierta": 1 }))).toBe("abierta");
    expect(posicionDe(corte, lector({ "-QM1.abierta": 0 }))).toBe("cerrada");
    expect(posicionDe(corte, lector({}))).toBeUndefined();
  });

  it("lo elegido en el 3D marca su aparato (cualquier pieza del cilindro)", () => {
    const simbolos = [{ designacion: "-MM1", tipo: "cilindro", caja: [0, 0, 1, 1], piezas: ["c1_cuerpo", "c1_vastago"] },
      { designacion: "-QM2", tipo: "valvula", caja: [0, 0, 1, 1], piezas: [] }];
    expect([...elegidosPor(simbolos, ["c1_vastago"])]).toEqual(["-MM1"]);
    expect(elegidosPor(simbolos, []).size).toBe(0);
  });

  it("las designaciones nunca bajan de 11 px; lo elegido se lee con su rótulo y sus bornes", () => {
    expect(altoTexto(3, 2)).toBe(MIN_TEXTO_PX / 2);
    expect(altoTexto(3, 5)).toBe(3);
    expect(detalleSimbolo({ rotulo: "Válvula 5/2 monoestable", bornes: ["A1: +TAB1-S2:14"] }))
      .toBe("Válvula 5/2 monoestable · bobina A1 → +TAB1-S2:14");
    expect(detalleSimbolo({})).toBe("");
  });

  it("lo elegido se nombra por lo que hace: los dos reguladores ya no se leen igual (nombres-por-funcion F4)", () => {
    const nombres = { "-RZ1": { rotulo: "Caudal de apertura" }, "-RZ2": { rotulo: "Caudal de cierre" } };
    const rz = (des: string) => nombreEnLinea(conNombre(des, nombres), detalleSimbolo({ rotulo: "Regulador de caudal" }));
    expect(rz("-RZ1")).toBe("Caudal de apertura · -RZ1 · Regulador de caudal");
    expect(rz("-RZ2")).toBe("Caudal de cierre · -RZ2 · Regulador de caudal");
    // sin el nombre del servidor, la designación manda: nunca una tabla de tipos de la UI
    expect(conNombre("-RZ3", nombres)).toEqual({ designacion: "-RZ3" });
    expect(conNombre("-RZ1", undefined)).toEqual({ designacion: "-RZ1" });
    // el rótulo por tipo que repite al detalle no se dice dos veces
    expect(nombreEnLinea(conNombre("-RZ5", { "-RZ5": { rotulo: "Silenciador" } }), "Silenciador")).toBe("Silenciador · -RZ5");
  });

  it("el cilindro por lo que hace, con su designación y sus medidas detrás", () => {
    const c = { designacion: "-MM1", ref: "x", piezas: [], diametro_mm: 32, vastago_mm: 12, carrera_mm: 200 };
    expect(nombreEnLinea(conNombre("-MM1", { "-MM1": { rotulo: "Cilindro de compuerta" } }), rotuloCilindro(c)))
      .toBe("Cilindro de compuerta · -MM1 · Ø32 mm, vástago 12 mm · carrera 200 mm");
  });

  it("se ajusta al ancho y, a pedido, se amplía a lo que se lee cómodo", () => {
    expect(escalaEsquema(600, 150)).toBe(4);
    expect(escalaEsquema(150, 150)).toBe(MIN_PX_MM);
    expect(escalaEsquema(300, 0)).toBe(MIN_PX_MM);
    expect(escalaEsquema(300, 150, true)).toBe(AMPLIADO_PX_MM);
    expect(escalaEsquema(900, 150, true)).toBe(6);
    expect(convieneAmpliar(360, 150)).toBe(true);
    expect(convieneAmpliar(600, 150)).toBe(false);
  });
});

describe("el detalle de un cilindro", () => {
  it("escribe sus cifras como la UI", () => {
    expect(rotuloCilindro({ designacion: "-MM1", ref: "x", piezas: [], diametro_mm: 32, vastago_mm: 12, carrera_mm: 200 }))
      .toBe("Ø32 mm, vástago 12 mm · carrera 200 mm");
    expect(textoFuerza({ F_avance_N: 482.5, F_avance_ef_N: 434.3, F_retroceso_N: 414.7, F_retroceso_ef_N: 373.2, p_bar: 6 }))
      .toEqual(["Avance 483 N (434 N efectivos)", "Retroceso 415 N (373 N efectivos)"]);
    expect(textoConsumo({ ciclo_NL: 2.2933, NL_min: 45.87, ciclos_min: 20 })).toBe("2,29 NL por ciclo · 45,9 NL/min a 20 ciclos/min");
    expect(textoConsumo({ ciclo_NL: 2.2933 })).toBe("2,29 NL por ciclo");
    const t = textoTiempo({ origen: "medido", escenario: "marcha", avance_s: 0.0934, retroceso_s: 0.0761 });
    expect(t.cifras).toBe("Avance 0,093 s · retroceso 0,076 s");
    expect(t.origen).toContain("«marcha»");
    expect(textoTiempo({ origen: "estimado", avance_s: 0.05 }).origen).toContain("estimado");
  });
});

describe("el aire de la barra", () => {
  it("la media móvil del caudal de los FRL en la ventana", () => {
    const h = new Historia(64);
    for (let k = 0; k <= 20; k++) h.empujar(k, ["-AZ1.Q_Nl_min"], [k % 2 ? 100 : 0]); // 0, 100, 0, …
    expect(senalesDeAire(["-AZ1.Q_Nl_min", "-AZ1.p_bar", "-MM1.x_mm", "-AZ1.Q_Nl_min"])).toEqual(["-AZ1.Q_Nl_min"]);
    // las últimas 10 s: t = 10 … 20 → 11 muestras, 5 de 100
    expect(aireMedio(h, ["-AZ1.Q_Nl_min"], 10)).toBeCloseTo(500 / 11, 6);
    expect(aireMedio(h, [], 10)).toBeUndefined();
    expect(aireMedio(new Historia(8), ["-AZ1.Q_Nl_min"])).toBeUndefined();
    expect(textoAire(45.87)).toBe("46 NL/min");
    expect(textoAire(4.58)).toBe("4,6 NL/min");
  });
});

describe("la sesión viva con aire", () => {
  const ini = {
    dispositivos: [{ designacion: "-QM2", tipo: "electrovalvula", ref: "V" },
      { designacion: "-MM1", tipo: "cilindro", ref: "C", pieza: "c1_cuerpo", carrera_mm: 200 },
      { designacion: "-AZ1", tipo: "frl", ref: "F" }],
  };

  it("el accionamiento manual lleva el lado o «0»; soltar uno vuelve a poner los demás", () => {
    expect(accionManual("-QM2", "14")).toEqual({ accion: "accionar_manual", dispositivo: "-QM2", valor: "14" });
    expect(alternarManual("-QM2", [], "14")).toEqual([accionManual("-QM2", "14")]);
    expect(alternarManual("-QM2", ["14", "12"], "14")).toEqual([accionManual("-QM2", "0"), accionManual("-QM2", "12")]);
  });

  it("la posición y el manual en palabras, con el número de puerto entre paréntesis", () => {
    expect(posicionPersona("12", ["14"])).toBe("reposo (12)");
    expect(posicionPersona("14", ["14"])).toBe("accionada (14)");
    expect(posicionPersona("0", ["14", "12"])).toBe("centro (0)");
    expect(posicionPersona("12", ["14", "12"])).toBe("lado 12");
    expect(posicionPersona(undefined, ["14"])).toBe("—");
    expect(manualPersona("0")).toBe("no");
    expect(manualPersona("14+12")).toBe("lado 14 y 12");
  });

  it("la posición se dice por su nombre, nunca «posición 14» (nombres-por-funcion F4)", () => {
    const estados = { 14: "Compuerta abierta", 12: "Compuerta cerrada" };
    expect(nombrePosicion("12", ["14"], estados)).toBe("Compuerta cerrada");
    expect(nombrePosicion("14", ["14"], estados)).toBe("Compuerta abierta");
    // sin declarar, el servidor manda la clave misma: eso no es un nombre
    expect(nombrePosicion("14", ["14"], { 14: "14", 12: "12" })).toBe("Accionada (14)");
    expect(nombrePosicion("12", ["14"])).toBe("Reposo (12)");
    expect(nombrePosicion(undefined, ["14"], estados)).toBeNull();
    expect(rotuloLado("14", false, true, estados)).toBe("Accionar a mano");
    expect(rotuloLado("14", true, true, estados)).toBe("Soltar");
    expect(rotuloLado("14", false, false, estados)).toBe("Accionar a mano · Compuerta abierta");
    expect(rotuloLado("12", true, false)).toBe("Soltar · 12");
  });

  it("las señales del aire se leen con su nombre, su unidad y sus palabras", () => {
    expect(rotuloAire("bobina14")).toBe("Bobina 14");
    expect(rotuloAire("pA_bar")).toBe("Presión de avance");
    expect(rotuloAire("rpm")).toBeUndefined();
    expect(leerValor(0, medidaDe("-QM2.bobina14"))).toBe("Apagada");
    expect(leerValor(1, medidaDe("-QM2.bobina14"))).toBe("Encendida");
    expect(leerValor(1, medidaDe("-QM1.abierta"))).toBe("Abierta");
    expect(leerValor(5.94, medidaDe("-MM1.pA_bar"))).toBe("5,94 bar");
    expect(leerValor(12.34, medidaDe("-AZ1.Q_Nl_min"))).toBe("12,3 NL/min");
    expect(leerValor(482.6, medidaDe("-MM1.F_N"))).toBe("483 N");
  });

  it("«Provocar atasco» sólo con un motor o una banda", () => {
    expect(hayAtasco({ bandas: [], dispositivos: [{ tipo: "cilindro" }, { tipo: "electrovalvula" }] })).toBe(false);
    expect(hayAtasco({ bandas: [], dispositivos: [{ tipo: "motor" }] })).toBe(true);
    expect(hayAtasco({ bandas: [{}], dispositivos: [] })).toBe(true);
  });

  it("lo enclavado se lee de la señal de la válvula (una fuente: también lo que puso el agente)", () => {
    expect(ladosManual(undefined)).toEqual([]);
    expect(ladosManual("0")).toEqual([]);
    expect(ladosManual("14")).toEqual(["14"]);
    expect(ladosManual("14+12")).toEqual(["14", "12"]);
  });

  it("la válvula aparece en Señales con su bobina y su posición", () => {
    const textos = textosDelArbol(ini, ["-QM2.posicion", "-K1.estado", "-QM2.averia", "-QM2.manual"]);
    expect(textos).toEqual(["-QM2.posicion", "-QM2.manual"]);
    const ramas = arbolDeSenales(ini, ["-QM2.bobina14", ...textos, "-MM1.x_mm"]);
    const qm2 = ramas.find((r) => r.clave === "-QM2")!;
    // sin rótulo del servidor, la designación sola (nombres-por-funcion D13: sin tabla de tipos)
    expect(qm2.titulo).toBe("-QM2");
    expect(qm2.designacion).toBeUndefined();
    expect(qm2.senales).toEqual(["-QM2.bobina14", "-QM2.posicion", "-QM2.manual"]);
    const conRotulo = arbolDeSenales({ dispositivos: ini.dispositivos.map((d) => ({ ...d, rotulo: d.designacion === "-MM1"
      ? "Cilindro de compuerta" : undefined })) }, ["-MM1.x_mm"]);
    expect(conRotulo).toEqual([{ clave: "-MM1", titulo: "Cilindro de compuerta", designacion: "-MM1", senales: ["-MM1.x_mm"] }]);
  });

  it("el cilindro dice su carrera y sus presiones, con la etiqueta 3D sólo elegido", () => {
    const [l] = lecturasDe(ini, ["-MM1.x_mm", "-MM1.pA_bar", "-MM1.pB_bar"]);
    expect(l.rotulo).toBeUndefined(); // sin rótulo del servidor, la fila muestra la designación (nombres-por-funcion D13)
    expect(l.soloElegida).toBe(true);
    const v: Record<string, number> = { "-MM1.x_mm": 199.6, "-MM1.pA_bar": 6, "-MM1.pB_bar": 0.04 };
    expect(textoLectura(l, (s) => v[s])).toBe("Carrera 200 mm · avance 6,0 bar · retroceso 0,0 bar");
    v["-MM1.x_mm"] = -0.8; // el tope blando de la junta lo pasa una fracción de mm
    expect(textoLectura(l, (s) => v[s])).toBe("Carrera 0 mm · avance 6,0 bar · retroceso 0,0 bar");
    v["-MM1.x_mm"] = 201.3; // y del otro lado, nunca más que la nominal
    expect(textoLectura(l, (s) => v[s])).toBe("Carrera 200 mm · avance 6,0 bar · retroceso 0,0 bar");
  });
});
