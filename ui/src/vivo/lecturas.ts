import type { InicioVivo } from "./protocolo";

/* Las lecturas de la máquina viva (plan V8.4 D5): qué valor se muestra de cada dispositivo, en
   el panel «Mandos» y, si tiene pieza 3D, en una etiqueta sobre ella. Motor: rpm e I; variador:
   frecuencia; PLC: su contador, si el programa tiene una variable que se llame así; relé de
   seguridad: sus salidas y, si no rearma por eso, que espera el ciclo de los dos canales
   (mandos-de-seguridad D3); cilindro: su carrera (entre 0 y la nominal: el tope blando de la junta
   la pasa una fracción de mm) y las presiones de avance y retroceso, con la etiqueta
   3D sólo si está elegido (V8.9 D12). Un dispositivo de otro tipo, o sin esas señales, no muestra
   nada. Puro. */

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
  /** Lo que se lee antes del valor: «A 6,0 bar». */
  prefijo?: string;
  /** Lo menos que se muestra: la carrera no baja de 0 (el tope blando de la junta la pasa
   *  una fracción de mm). */
  piso?: number;
  /** Lo más que se muestra: la carrera nominal. */
  techo?: number;
}

export interface Lectura {
  designacion: string;
  tipo: string;
  /** Lo que HACE el aparato, del servidor (`rotulo` del `inicio`, plan nombres-por-funcion D13):
   *  «Motor de mezcla», «Seguridad del recipiente». Sin él, la fila muestra la designación. */
  rotulo?: string;
  /** La frase de su ⓘ, si el modelador la escribió. */
  descripcion?: string;
  pieza?: string;
  lineas: LineaLectura[];
  /** Su etiqueta 3D sólo con la pieza elegida (el cilindro, V8.9 D12: con varios, una maraña). */
  soloElegida?: boolean;
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
    let lineas: LineaLectura[] = [];
    if (d.tipo === "motor") {
      lineas = [
        { senal: `${d.designacion}.rpm`, unidad: "rpm", decimales: 0 },
        { senal: `${d.designacion}.I_A`, unidad: "A", decimales: 1 },
      ];
    } else if (d.tipo === "variador") {
      lineas = [{ senal: `${d.designacion}.f_Hz`, unidad: "Hz", decimales: 1 }];
    } else if (d.tipo === "plc") {
      const c = senalContador(d.designacion, nombres);
      lineas = c ? [{ senal: c, unidad: "", decimales: 0, prefijo: "Contador" }] : [];
    } else if (d.tipo === "rele_seguridad") {
      lineas = [
        { senal: `${d.designacion}.salidas`, unidad: "", decimales: 0, si: "Habilita la marcha", no: "Corta la marcha" },
        // con los dos canales cerrados es la razón por la que no rearma (un canal pegado)
        { senal: `${d.designacion}.espera_ciclo`, unidad: "", decimales: 0,
          si: "No rearma hasta que abran y cierren los dos canales.", no: "", nota: true,
          cuando: [`${d.designacion}.canal1`, `${d.designacion}.canal2`] },
      ];
    } else if (d.tipo === "cilindro") {
      lineas = [
        { senal: `${d.designacion}.x_mm`, unidad: "mm", decimales: 0, prefijo: "Carrera", piso: 0,
          ...(d.carrera_mm ? { techo: d.carrera_mm } : {}) },
        { senal: `${d.designacion}.pA_bar`, unidad: "bar", decimales: 1, prefijo: "avance" },
        { senal: `${d.designacion}.pB_bar`, unidad: "bar", decimales: 1, prefijo: "retroceso" },
      ];
    }
    lineas = lineas.filter((l) => hay.has(l.senal));
    if (lineas.length) {
      out.push({ designacion: d.designacion, tipo: d.tipo, pieza: d.pieza, lineas,
        ...(d.rotulo ? { rotulo: d.rotulo } : {}), ...(d.descripcion ? { descripcion: d.descripcion } : {}),
        ...(d.tipo === "cilindro" ? { soloElegida: true } : {}) });
    }
  }
  return out;
}

/** Las líneas de una lectura en una frase («1 799 rpm · 3,8 A»); la que no dice nada se salta.
 *  Con `notas`, las que van en la nota bajo la fila. */
export function textoLectura(l: Pick<Lectura, "lineas">, valor: (senal: string) => number | undefined, notas = false): string {
  return l.lineas
    .filter((ln) => !!ln.nota === notas)
    .filter((ln) => !ln.cuando || ln.cuando.every((s) => encendida(valor(s))))
    .map((ln) => {
      const v = valor(ln.senal);
      const acotado = v === undefined ? v : Math.min(ln.techo ?? Infinity, Math.max(ln.piso ?? -Infinity, v));
      const t = formatear(acotado, ln);
      return t && ln.prefijo ? `${ln.prefijo} ${t}` : t;
    }).filter(Boolean).join(notas ? " " : " · ");
}

function encendida(v: number | undefined): boolean {
  return v !== undefined && Number.isFinite(v) && v >= 0.5;
}

/** «1 799 rpm», «3,8 A», «—» si no hay valor. Coma decimal, espacio fino de miles y la unidad tras
 *  un espacio duro (como `cifra`, F5b). Una de sí o no, su palabra. */
export function formatear(valor: number | undefined, l: Pick<LineaLectura, "unidad" | "decimales" | "si" | "no">): string {
  if (valor === undefined || !Number.isFinite(valor)) return l.si !== undefined && l.no === "" ? "" : "—";
  if (l.si !== undefined) return valor >= 0.5 ? l.si : l.no ?? "";
  const [ent, dec] = Math.abs(valor).toFixed(l.decimales).split(".");
  const miles = ent.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const signo = valor < 0 && Number(Math.abs(valor).toFixed(l.decimales)) !== 0 ? "−" : "";
  const num = `${signo}${miles}${dec ? `,${dec}` : ""}`;
  return l.unidad ? `${num} ${l.unidad}` : num;
}
