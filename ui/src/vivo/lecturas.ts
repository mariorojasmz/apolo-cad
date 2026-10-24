import type { InicioVivo } from "./protocolo";

/* Las lecturas de la máquina viva (plan V8.4 D5): qué valor se muestra de cada dispositivo, en
   el panel «Mandos» y, si tiene pieza 3D, en una etiqueta sobre ella. Motor: rpm e I; variador:
   frecuencia; PLC: su contador, si el programa tiene una variable que se llame así; relé de
   seguridad: sus salidas y, si no rearma por eso, que espera el ciclo de los dos canales
   (mandos-de-seguridad D3). Un dispositivo de otro tipo, o sin esas señales, no muestra nada. Puro. */

export interface LineaLectura {
  senal: string;
  unidad: string;
  decimales: number;
  /** Una señal de sí o no se lee en palabras: `si` con 1, `no` con 0 («» no muestra nada). */
  si?: string;
  no?: string;
  /** Se muestra sólo con estas señales en 1 (si no, se salta). */
  cuando?: string[];
  /** Una frase, no un valor: va en una nota bajo la fila del panel (no en la etiqueta 3D). */
  nota?: boolean;
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
    } else if (d.tipo === "rele_seguridad") {
      rotulo = "Relé de seguridad";
      lineas = [
        { senal: `${d.designacion}.salidas`, unidad: "", decimales: 0, si: "Salidas cerradas", no: "Salidas abiertas" },
        // con los dos canales cerrados es la razón por la que no rearma (un canal pegado)
        { senal: `${d.designacion}.espera_ciclo`, unidad: "", decimales: 0,
          si: "No rearma hasta que abran y cierren los dos canales.", no: "", nota: true,
          cuando: [`${d.designacion}.canal1`, `${d.designacion}.canal2`] },
      ];
    }
    lineas = lineas.filter((l) => hay.has(l.senal));
    if (lineas.length) out.push({ designacion: d.designacion, tipo: d.tipo, rotulo, pieza: d.pieza, lineas });
  }
  return out;
}

/** Las líneas de una lectura en una frase («1 799 rpm · 3,8 A»); la que no dice nada se salta.
 *  Con `notas`, las que van en la nota bajo la fila. */
export function textoLectura(l: Pick<Lectura, "lineas">, valor: (senal: string) => number | undefined, notas = false): string {
  return l.lineas
    .filter((ln) => !!ln.nota === notas)
    .filter((ln) => !ln.cuando || ln.cuando.every((s) => encendida(valor(s))))
    .map((ln) => formatear(valor(ln.senal), ln)).filter(Boolean).join(notas ? " " : " · ");
}

function encendida(v: number | undefined): boolean {
  return v !== undefined && Number.isFinite(v) && v >= 0.5;
}

/** «1 799 rpm», «3,8 A», «—» si no hay valor. Coma decimal y espacio fino de miles. Una de sí o
 *  no, su palabra. */
export function formatear(valor: number | undefined, l: Pick<LineaLectura, "unidad" | "decimales" | "si" | "no">): string {
  if (valor === undefined || !Number.isFinite(valor)) return l.si !== undefined && l.no === "" ? "" : "—";
  if (l.si !== undefined) return valor >= 0.5 ? l.si : l.no ?? "";
  const [ent, dec] = Math.abs(valor).toFixed(l.decimales).split(".");
  const miles = ent.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const signo = valor < 0 && Number(Math.abs(valor).toFixed(l.decimales)) !== 0 ? "−" : "";
  const num = `${signo}${miles}${dec ? `,${dec}` : ""}`;
  return l.unidad ? `${num} ${l.unidad}` : num;
}
