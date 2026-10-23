import type { InicioVivo } from "./protocolo";

/* Las lecturas de la máquina viva (plan V8.4 D5): qué valor se muestra de cada dispositivo, en
   el panel «Mandos» y, si tiene pieza 3D, en una etiqueta sobre ella. Motor: rpm e I; variador:
   frecuencia; PLC: su contador, si el programa tiene una variable que se llame así. Un
   dispositivo de otro tipo, o sin esas señales, no muestra nada. Puro. */

export interface LineaLectura {
  senal: string;
  unidad: string;
  decimales: number;
}

export interface Lectura {
  designacion: string;
  tipo: string;
  /** Rótulo corto del dispositivo: «Motor», «Variador», «Contador del PLC». */
  rotulo: string;
  pieza?: string;
  lineas: LineaLectura[];
}

/** Una variable de un programa del PLC que cuenta: `-K1.Main.cuenta`, `-K1.P1.contador`. */
const CONTADOR = /^(cuenta|contador|conteo|count|cnt)/i;

export function senalContador(plc: string, nombres: readonly string[]): string | null {
  const pref = `${plc}.`;
  for (const n of nombres) {
    if (!n.startsWith(pref)) continue;
    const partes = n.slice(pref.length).split(".");
    if (partes.length === 2 && CONTADOR.test(partes[1])) return n;
  }
  return null;
}

export function lecturasDe(ini: Pick<InicioVivo, "dispositivos">, nombres: readonly string[]): Lectura[] {
  const hay = new Set(nombres);
  const out: Lectura[] = [];
  for (const d of ini.dispositivos) {
    let rotulo = "";
    let lineas: LineaLectura[] = [];
    if (d.tipo === "motor") {
      rotulo = "Motor";
      lineas = [
        { senal: `${d.designacion}.rpm`, unidad: "rpm", decimales: 0 },
        { senal: `${d.designacion}.I_A`, unidad: "A", decimales: 1 },
      ];
    } else if (d.tipo === "variador") {
      rotulo = "Variador";
      lineas = [{ senal: `${d.designacion}.f_Hz`, unidad: "Hz", decimales: 1 }];
    } else if (d.tipo === "plc") {
      rotulo = "Contador del PLC";
      const c = senalContador(d.designacion, nombres);
      lineas = c ? [{ senal: c, unidad: "", decimales: 0 }] : [];
    }
    lineas = lineas.filter((l) => hay.has(l.senal));
    if (lineas.length) out.push({ designacion: d.designacion, tipo: d.tipo, rotulo, pieza: d.pieza, lineas });
  }
  return out;
}

/** «1 799 rpm», «3,8 A», «—» si no hay valor. Coma decimal y espacio fino de miles. */
export function formatear(valor: number | undefined, l: Pick<LineaLectura, "unidad" | "decimales">): string {
  if (valor === undefined || !Number.isFinite(valor)) return "—";
  const [ent, dec] = Math.abs(valor).toFixed(l.decimales).split(".");
  const miles = ent.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const signo = valor < 0 && Number(Math.abs(valor).toFixed(l.decimales)) !== 0 ? "−" : "";
  const num = `${signo}${miles}${dec ? `,${dec}` : ""}`;
  return l.unidad ? `${num} ${l.unidad}` : num;
}
