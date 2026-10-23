import { describe, expect, it } from "vitest";
import {
  declaraciones, indiceSenales, lineasDelPrograma, programasDelDocumento, tiposDeSenales, tramos, valorSt,
  type Fragmento,
} from "./programa";

/* El programa vivo del PLC (plan V8.4 D8): el texto ST con cada variable marcada y su señal
   (`-K1.v` la global, `-K1.Main.v` la local), sin tomar comentarios ni campos de bloques. */

const FUENTE = `VAR_GLOBAL
  pb_marcha AT %IX0.0 : BOOL;   (* -S1 marcha, NA *)
  foto      AT %IX0.3 : BOOL;
  q_marcha  AT %QX0.0 : BOOL;
END_VAR

PROGRAM Main
VAR
  en_marcha  : BOOL;
  cuenta     : INT;    (* cajas contadas por -B1 *)
  r_foto     : R_TRIG;
  t_listo    : TON;    (* 200 ms tras
                          el arranque *)
END_VAR
t_listo(IN := TRUE, PT := T#200ms);
r_foto(CLK := foto);
IF r_foto.Q THEN cuenta := cuenta + 1; END_IF; // pb_marcha no se cuenta aquí
IF PB_MARCHA AND t_listo.Q THEN en_marcha := TRUE; END_IF;
q_marcha := en_marcha;
END_PROGRAM
`;

const NOMBRES = indiceSenales([
  "-K1.%IX0.0", "-K1.pb_marcha", "-K1.foto", "-K1.q_marcha", "-K1.Main.en_marcha", "-K1.Main.cuenta", "-M1.rpm",
]);

const vars = (ln: Fragmento[]) =>
  ln.filter((f): f is Extract<Fragmento, { tipo: "variable" }> => f.tipo === "variable").map((f) => [f.texto, f.senal]);

describe("programa ST vivo", () => {
  it("los comentarios de bloque siguen en la línea que viene", () => {
    const t = tramos(FUENTE);
    const i = FUENTE.split("\n").findIndex((l) => l.includes("el arranque"));
    expect(t[i]).toEqual([{ texto: "                          el arranque *)", comentario: true }]);
    expect(tramos("a := 1; // nota (* no abre *)\nb := 2;")[1]).toEqual([{ texto: "b := 2;", comentario: false }]);
  });

  it("declara globales y locales con su tipo", () => {
    expect(declaraciones(FUENTE)).toEqual([
      { nombre: "pb_marcha", tipo: "BOOL", programa: null },
      { nombre: "foto", tipo: "BOOL", programa: null },
      { nombre: "q_marcha", tipo: "BOOL", programa: null },
      { nombre: "en_marcha", tipo: "BOOL", programa: "Main" },
      { nombre: "cuenta", tipo: "INT", programa: "Main" },
      { nombre: "r_foto", tipo: "R_TRIG", programa: "Main" },
      { nombre: "t_listo", tipo: "TON", programa: "Main" },
    ]);
  });

  it("cada variable con su señal: global -K1.v, local -K1.Main.v; las instancias, sin señal", () => {
    const lineas = lineasDelPrograma(FUENTE, "-K1", NOMBRES);
    const de = (frag: string) => vars(lineas[FUENTE.split("\n").findIndex((l) => l.includes(frag))]);
    expect(de("pb_marcha AT")).toEqual([["pb_marcha", "-K1.pb_marcha"]]);
    expect(de("cuenta     : INT")).toEqual([["cuenta", "-K1.Main.cuenta"]]);
    // `r_foto.Q`: la instancia no es señal y `.Q` es un campo; lo del comentario no cuenta
    expect(de("IF r_foto.Q")).toEqual([["r_foto", null], ["cuenta", "-K1.Main.cuenta"], ["cuenta", "-K1.Main.cuenta"]]);
    // el ST no distingue mayúsculas: PB_MARCHA es pb_marcha
    expect(de("IF PB_MARCHA")).toEqual([["PB_MARCHA", "-K1.pb_marcha"], ["t_listo", null], ["en_marcha", "-K1.Main.en_marcha"]]);
    expect(de("q_marcha := en_marcha")).toEqual([["q_marcha", "-K1.q_marcha"], ["en_marcha", "-K1.Main.en_marcha"]]);
    // el texto se reconstruye entero
    lineas.forEach((ln, i) => expect(ln.map((f) => f.texto).join("")).toBe(FUENTE.split("\n")[i]));
  });

  it("valores como el monitor de un PLC", () => {
    expect(valorSt(1, "BOOL")).toBe("TRUE");
    expect(valorSt(0, "BOOL")).toBe("FALSE");
    expect(valorSt(7, "INT")).toBe("7");
    expect(valorSt(2.345, "REAL")).toBe("2,35");
    expect(valorSt(undefined, "INT")).toBe("—");
  });

  it("los programas salen del log y dan el tipo de cada señal", () => {
    const progs = programasDelDocumento([
      { id: "c1", type: "add_box", params: {} },
      { id: "c1636", type: "add_program", params: { plc: "-K1", fuente: FUENTE, ciclo_ms: 10 } },
    ]);
    expect(progs).toEqual([{ plc: "-K1", fuente: FUENTE, ciclo_ms: 10, comando: "c1636" }]);
    const tipos = tiposDeSenales(progs, NOMBRES);
    expect(tipos.get("-K1.Main.cuenta")).toBe("INT");
    expect(tipos.get("-K1.pb_marcha")).toBe("BOOL");
    expect(tipos.has("-M1.rpm")).toBe(false);
  });
});
