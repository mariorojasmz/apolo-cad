/* La unidad y la forma de leer una señal por su NOMBRE (plan V8.4 D7): `-M1.rpm` → rpm,
   `-M1.I_A` → A, `-Q1.cerrado` → sí/no. Lo usan el árbol de señales, el multímetro y el
   osciloscopio. Los nombres son los de la co-simulación (D10 de V8.3): la magnitud va al final,
   tras un «_» (`I_A`, `f_Hz`, `termico_pct`) o sola (`rpm`). Puro. */

import { cifra } from "../diseno/cifra";

export interface Medida {
  unidad: string;
  decimales: number;
  /** 0/1: se lee «Sí»/«No» (o `si`/`no`) y su escala es fija. */
  booleana: boolean;
  si?: string;
  no?: string;
}

const SUFIJOS: [RegExp, string, number][] = [
  [/(^|_)rpm$/i, "rpm", 0],
  [/_m_s$/i, "m/s", 2],
  [/_A$/, "A", 2],
  [/_V$/, "V", 1],
  [/_Hz$/, "Hz", 1],
  [/_Nm$/, "N·m", 2],
  [/_W$/, "W", 0],
  [/_pct$/, "%", 1],
  [/_mm$/, "mm", 0],
  [/_ohm$/, "Ω", 3],
  // el aire (V8.9 D7)
  [/_bar$/, "bar", 2],
  [/_Nl_min$/, "NL/min", 1],
  [/_NL$/, "NL", 2],
  [/_N$/, "N", 0],
];

/** Lo que es sí o no y tiene sus palabras: la bobina de una válvula, la válvula de corte (V8.9). */
const PALABRAS: [RegExp, string, string][] = [
  [/^bobina\d*$/i, "Encendida", "Apagada"],
  [/^abierta$/i, "Abierta", "Cerrada"],
];

/** Lo que es sí o no: estados de contactos, protecciones, pilotos, entradas y salidas. */
const BOOLEANAS = /^(cerrado|abierto|disparado|conectada|conectado|fases_ok|limitando|ok|rele_falla|sto|par_habilitado|alimentado|accionado|encendido|activo|retenida|enclavado)$/i;
/** Una entrada o salida digital del PLC: `%IX0.0`, `%QX1.1`. */
const BIT_PLC = /^%[IQM]X\d+\.\d+$/i;

/** La magnitud: lo que va después de la designación (`-M1.rpm` → `rpm`; `-K1.%IX0.0` → `%IX0.0`). */
export function magnitud(senal: string): string {
  const i = senal.indexOf(".");
  return i < 0 ? senal : senal.slice(i + 1);
}

/** Unidad y decimales de una señal. `tipoPlc` (BOOL, INT, REAL…) manda cuando se conoce. */
export function medidaDe(senal: string, tipoPlc?: string): Medida {
  if (tipoPlc) {
    const t = tipoPlc.toUpperCase();
    if (t === "BOOL") return { unidad: "", decimales: 0, booleana: true };
    if (/INT$/.test(t) || t === "BYTE" || t === "WORD" || t === "DWORD") return { unidad: "", decimales: 0, booleana: false };
    return { unidad: "", decimales: 2, booleana: false };
  }
  const m = magnitud(senal);
  const ultima = m.slice(m.lastIndexOf(".") + 1);
  for (const [re, si, no] of PALABRAS) if (re.test(ultima)) return { unidad: "", decimales: 0, booleana: true, si, no };
  if (BOOLEANAS.test(ultima) || BIT_PLC.test(m)) return { unidad: "", decimales: 0, booleana: true };
  for (const [re, unidad, decimales] of SUFIJOS) if (re.test(m)) return { unidad, decimales, booleana: false };
  return { unidad: "", decimales: 2, booleana: false };
}

/** «1 799 rpm», «3,81 A», «Sí» / «No», «—» sin valor. Coma decimal y espacio fino de miles. */
export function leerValor(valor: number | undefined, m: Medida): string {
  if (valor === undefined || !Number.isFinite(valor)) return "—";
  if (m.booleana) return valor >= 0.5 ? m.si ?? "Sí" : m.no ?? "No";
  return cifra(valor, m.decimales, m.unidad);
}
