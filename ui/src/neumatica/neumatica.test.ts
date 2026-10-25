import { describe, expect, it } from "vitest";
import { Historia } from "../vivo/historia";
import { textosDelArbol, arbolDeSenales } from "../vivo/arbolSenales";
import { lecturasDe, textoLectura } from "../vivo/lecturas";
import { aireMedio, senalesDeAire, textoAire } from "./aire";
import {
  AMPLIADO_PX_MM, bordesLeyenda, colorPresion, convieneAmpliar, elegidosPor, escalaEsquema, MIN_PX_MM, pasoDe, posicionDe, presionDe, RAMPA_PRESION,
  rotuloCilindro, textoConsumo, textoFuerza, textoTiempo, type Lector,
} from "./esquema";
import { accionManual, alternarManual, ladosManual } from "./manual";
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
  it("cinco pasos de un solo tono, del oscuro (sin presión) al claro (la regulada)", () => {
    expect(RAMPA_PRESION).toHaveLength(5);
    expect(pasoDe(0, 6)).toBe(0);
    expect(pasoDe(6, 6)).toBe(4);
    expect(pasoDe(9, 6)).toBe(4);
    expect(pasoDe(3, 6)).toBe(2);
    expect(colorPresion(undefined, 6)).toBeNull();
    expect(colorPresion(6, 6)).toBe(RAMPA_PRESION[4]);
  });

  it("la leyenda dice sus bordes con coma decimal", () => {
    expect(bordesLeyenda(6)).toEqual(["0", "1,2", "2,4", "3,6", "4,8", "6"]);
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
      .toBe("Ø32/12 · carrera 200 mm");
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
    dispositivos: [{ designacion: "-QM2", tipo: "electrovalvula", ref: "V" }, { designacion: "-MM1", tipo: "cilindro", ref: "C", pieza: "c1_cuerpo" },
      { designacion: "-AZ1", tipo: "frl", ref: "F" }],
  };

  it("el accionamiento manual lleva el lado o «0»; soltar uno vuelve a poner los demás", () => {
    expect(accionManual("-QM2", "14")).toEqual({ accion: "accionar_manual", dispositivo: "-QM2", valor: "14" });
    expect(alternarManual("-QM2", [], "14")).toEqual([accionManual("-QM2", "14")]);
    expect(alternarManual("-QM2", ["14", "12"], "14")).toEqual([accionManual("-QM2", "0"), accionManual("-QM2", "12")]);
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
    expect(qm2.rotulo).toBe("Electroválvula");
    expect(qm2.senales).toEqual(["-QM2.bobina14", "-QM2.posicion", "-QM2.manual"]);
    expect(ramas.find((r) => r.clave === "-MM1")!.rotulo).toBe("Cilindro");
  });

  it("el cilindro dice su carrera y sus presiones, con la etiqueta 3D sólo elegido", () => {
    const [l] = lecturasDe(ini, ["-MM1.x_mm", "-MM1.pA_bar", "-MM1.pB_bar"]);
    expect(l.rotulo).toBe("Cilindro");
    expect(l.soloElegida).toBe(true);
    const v: Record<string, number> = { "-MM1.x_mm": 199.6, "-MM1.pA_bar": 6, "-MM1.pB_bar": 0.04 };
    expect(textoLectura(l, (s) => v[s])).toBe("Carrera 200 mm · A 6,0 bar · B 0,0 bar");
    v["-MM1.x_mm"] = -0.8; // el tope blando de la junta lo pasa una fracción de mm
    expect(textoLectura(l, (s) => v[s])).toBe("Carrera 0 mm · A 6,0 bar · B 0,0 bar");
  });
});
