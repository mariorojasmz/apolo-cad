import type { CommandRecord } from "../types";

/* El programa vivo del PLC (plan V8.4 D8): el texto ST de cada programa con el valor actual de
   cada variable al lado, como el monitor online de un PLC. El texto sale del log de comandos
   que la UI ya tiene (`add_program` → `fuente`); los valores, de las señales de la sesión viva:
   una variable global `v` del PLC `-K1` es la señal `-K1.v`, y una local de `PROGRAM Main`,
   `-K1.Main.v` (nombres de la co-simulación; el ST no distingue mayúsculas). Las instancias de
   bloques (`TON`, `R_TRIG`) no son señales: van sin valor. Puro. */

export interface FuentePlc {
  plc: string;
  fuente: string;
  ciclo_ms?: number;
  comando: string;
}

/** Los programas del documento, en el orden del log. */
export function programasDelDocumento(commands: readonly CommandRecord[]): FuentePlc[] {
  const out: FuentePlc[] = [];
  for (const c of commands) {
    if (c.type !== "add_program") continue;
    const { plc, fuente, ciclo_ms } = c.params as { plc?: unknown; fuente?: unknown; ciclo_ms?: unknown };
    if (typeof plc !== "string" || typeof fuente !== "string") continue;
    out.push({ plc, fuente, comando: c.id, ...(typeof ciclo_ms === "number" ? { ciclo_ms } : {}) });
  }
  return out;
}

// ── el texto, sin comentarios ───────────────────────────────────────────────────────────────

interface Tramo {
  texto: string;
  comentario: boolean;
}

/** Cada línea partida en tramos de código y de comentario (`(* … *)` y `// …`; un comentario
 *  de bloque puede seguir en las líneas que vienen). */
export function tramos(fuente: string): Tramo[][] {
  const lineas = fuente.replace(/\r\n?/g, "\n").split("\n");
  let enBloque = false;
  return lineas.map((ln) => {
    const out: Tramo[] = [];
    let i = 0;
    while (i < ln.length) {
      if (enBloque) {
        const fin = ln.indexOf("*)", i);
        const j = fin < 0 ? ln.length : fin + 2;
        out.push({ texto: ln.slice(i, j), comentario: true });
        if (fin >= 0) enBloque = false;
        i = j;
        continue;
      }
      const a = ln.indexOf("(*", i);
      const b = ln.indexOf("//", i);
      const c = [a, b].filter((x) => x >= 0).sort((x, y) => x - y)[0];
      if (c === undefined) {
        out.push({ texto: ln.slice(i), comentario: false });
        break;
      }
      if (c > i) out.push({ texto: ln.slice(i, c), comentario: false });
      if (c === b && (a < 0 || b < a)) {
        out.push({ texto: ln.slice(c), comentario: true });
        break;
      }
      enBloque = true;
      i = c;
      const fin = ln.indexOf("*)", c + 2);
      const j = fin < 0 ? ln.length : fin + 2;
      out.push({ texto: ln.slice(c, j), comentario: true });
      if (fin >= 0) enBloque = false;
      i = j;
    }
    return out;
  });
}

// ── las declaraciones ───────────────────────────────────────────────────────────────────────

export interface VariableSt {
  nombre: string;
  tipo: string;
  /** El PROGRAM que la declara (null = `VAR_GLOBAL`). */
  programa: string | null;
}

const DECL = /^\s*([A-Za-z_]\w*)\s*(?:AT\s+%[\w.]+\s*)?:\s*([A-Za-z_]\w*)/i;

/** Las variables de los bloques `VAR_GLOBAL` y de los `VAR` de cada `PROGRAM`. */
export function declaraciones(fuente: string): VariableSt[] {
  const out: VariableSt[] = [];
  let programa: string | null = null;
  let bloque: "global" | "local" | "otro" | null = null;
  for (const linea of tramos(fuente)) {
    const codigo = linea.filter((t) => !t.comentario).map((t) => t.texto).join(" ");
    for (const sentencia of codigo.split(";")) {
      const s = sentencia.trim();
      if (!s) continue;
      const p = /^PROGRAM\s+([A-Za-z_]\w*)/i.exec(s);
      if (p) programa = p[1];
      if (/^END_PROGRAM\b/i.test(s)) programa = null;
      if (/^VAR_GLOBAL\b/i.test(s)) bloque = "global";
      else if (/^VAR(_INPUT|_OUTPUT|_IN_OUT)?\b/i.test(s) && !/^VAR_GLOBAL/i.test(s)) bloque = programa ? "local" : "otro";
      else if (/^END_VAR\b/i.test(s)) bloque = null;
      else if (bloque === "global" || bloque === "local") {
        const d = DECL.exec(s);
        if (d) out.push({ nombre: d[1], tipo: d[2].toUpperCase(), programa: bloque === "global" ? null : programa });
      }
    }
  }
  return out;
}

/** La señal de una variable entre los nombres de la sesión (sin distinguir mayúsculas). */
export function senalDeVariable(plc: string, v: VariableSt, nombres: ReadonlyMap<string, string>): string | null {
  const clave = (v.programa ? `${plc}.${v.programa}.${v.nombre}` : `${plc}.${v.nombre}`).toLowerCase();
  return nombres.get(clave) ?? null;
}

/** Índice minúsculas → nombre real de las señales. */
export function indiceSenales(nombres: Iterable<string>): Map<string, string> {
  const m = new Map<string, string>();
  for (const n of nombres) m.set(n.toLowerCase(), n);
  return m;
}

// ── las líneas para mostrar ─────────────────────────────────────────────────────────────────

export type Fragmento =
  | { tipo: "codigo"; texto: string }
  | { tipo: "comentario"; texto: string }
  | { tipo: "variable"; texto: string; senal: string | null; variable: VariableSt };

const IDENT = /[A-Za-z_]\w*/g;

/** Las líneas del programa con cada uso de una variable marcado (y su señal, si la hay). Un
 *  nombre después de un punto (`t_listo.Q`) es un campo, no una variable. */
export function lineasDelPrograma(fuente: string, plc: string, nombres: ReadonlyMap<string, string>): Fragmento[][] {
  const vars = declaraciones(fuente);
  const globales = new Map(vars.filter((v) => !v.programa).map((v) => [v.nombre.toLowerCase(), v]));
  const locales = new Map<string, Map<string, VariableSt>>();
  for (const v of vars) {
    if (!v.programa) continue;
    const k = v.programa.toLowerCase();
    if (!locales.has(k)) locales.set(k, new Map());
    locales.get(k)!.set(v.nombre.toLowerCase(), v);
  }
  let programa: string | null = null;
  let esperaNombre = false;
  return tramos(fuente).map((linea) => {
    const out: Fragmento[] = [];
    for (const tr of linea) {
      if (tr.comentario) {
        out.push({ tipo: "comentario", texto: tr.texto });
        continue;
      }
      let i = 0;
      for (const m of tr.texto.matchAll(IDENT)) {
        const id = m[0];
        const at = m.index ?? 0;
        const upper = id.toUpperCase();
        if (esperaNombre) {
          programa = id;
          esperaNombre = false;
        } else if (upper === "PROGRAM") {
          esperaNombre = true;
        } else if (upper === "END_PROGRAM") {
          programa = null;
        }
        const campo = at > 0 && tr.texto[at - 1] === ".";
        const v = campo ? undefined
          : (programa ? locales.get(programa.toLowerCase())?.get(id.toLowerCase()) : undefined) ?? globales.get(id.toLowerCase());
        if (!v) continue;
        if (at > i) out.push({ tipo: "codigo", texto: tr.texto.slice(i, at) });
        out.push({ tipo: "variable", texto: id, senal: senalDeVariable(plc, v, nombres), variable: v });
        i = at + id.length;
      }
      if (i < tr.texto.length) out.push({ tipo: "codigo", texto: tr.texto.slice(i) });
    }
    return out;
  });
}

/** El valor como lo muestra el monitor de un PLC: TRUE/FALSE, entero o real. */
export function valorSt(v: number | undefined, tipo: string): string {
  if (v === undefined || !Number.isFinite(v)) return "—";
  if (tipo === "BOOL") return v >= 0.5 ? "TRUE" : "FALSE";
  if (/INT$|^(BYTE|WORD|DWORD)$/.test(tipo)) return String(Math.round(v));
  return (Math.round(v * 100) / 100).toString().replace(".", ",");
}

/** El tipo ST de cada señal de variable (para leerlas bien en el multímetro y el osciloscopio). */
export function tiposDeSenales(programas: readonly FuentePlc[], nombres: ReadonlyMap<string, string>): Map<string, string> {
  const out = new Map<string, string>();
  for (const p of programas) {
    for (const v of declaraciones(p.fuente)) {
      const s = senalDeVariable(p.plc, v, nombres);
      if (s) out.set(s, v.tipo);
    }
  }
  return out;
}
