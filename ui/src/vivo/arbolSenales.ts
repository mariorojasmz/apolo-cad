import type { InicioVivo } from "./protocolo";

/* El árbol de señales de la sesión viva (plan V8.4 D7): dispositivo → señales, de la tabla del
   `inicio` y de las que llegan después (mensaje `senales`). Las señales de un dispositivo del
   tablero (`-M1.rpm`, `-K1.Main.cuenta`, `-W3.1.I_A`) van bajo su designación, con el rótulo de
   su tipo; las corrientes de conductores sueltos (`c1620#1.I_A`) se juntan en «Conductores» y
   lo mecánico (banda, cajas) en «Máquina». Puro. */

export interface RamaSenales {
  /** Clave estable (la designación o el nombre del grupo). */
  clave: string;
  titulo: string;
  /** Rótulo corto del tipo («Motor», «Variador», «PLC»), si se conoce. */
  rotulo?: string;
  senales: string[];
}

const TIPOS: Record<string, string> = {
  motor: "Motor", variador: "Variador", plc: "PLC", pulsador: "Pulsador", seta: "Seta de emergencia",
  selector: "Selector", seccionador: "Seccionador", piloto: "Piloto", sensor: "Sensor",
  contactor: "Contactor", rele: "Relé", guardamotor: "Guardamotor", itm: "Interruptor termomagnético",
  rele_termico: "Relé térmico", fusible: "Fusible", fuente: "Fuente", red: "Red",
  resguardo: "Interruptor de resguardo", rele_seguridad: "Relé de seguridad",
  diferencial: "Interruptor diferencial", hmi: "Panel de operador",
  electrovalvula: "Electroválvula", cilindro: "Cilindro", frl: "Filtro-regulador", valvula_corte: "Válvula de corte",
};

/** Las señales de TEXTO que van en el árbol (V8.9 D12): la posición de cada electroválvula
 *  («14», «12», «0») y su accionamiento manual enclavado, junto a sus bobinas. Las demás de texto
 *  (estado del PLC, falla) tienen su lugar en «Mandos» y «PLC». */
export function textosDelArbol(ini: Pick<InicioVivo, "dispositivos">, textos: Iterable<string>): string[] {
  const valvulas = new Set(ini.dispositivos.filter((d) => d.tipo === "electrovalvula").map((d) => d.designacion));
  return [...textos].filter((n) => (n.endsWith(".posicion") || n.endsWith(".manual"))
    && valvulas.has(designacionDe(n) ?? ""));
}

/** La designación de una señal de tablero (`-M1`, `=F1-Q1`, `+TAB1-K1`), o null. */
export function designacionDe(senal: string): string | null {
  if (!/^[-=+]/.test(senal)) return null;
  const i = senal.indexOf(".");
  return i < 0 ? senal : senal.slice(0, i);
}

/** La corriente de un conductor (`c1620#1.I_A`); `c119.v_m_s` es una pieza (la banda). */
const CONDUCTOR = /^c\d+(#\d+)?\.I_A$/;

/** Agrupa las señales: primero los dispositivos en el orden del tablero, después los que sólo
 *  aparecen en las señales (cables), «Conductores» y «Máquina». Dentro, en el orden de llegada. */
export function arbolDeSenales(ini: Pick<InicioVivo, "dispositivos">, nombres: readonly (string | undefined)[]): RamaSenales[] {
  const ramas = new Map<string, RamaSenales>();
  for (const d of ini.dispositivos) {
    ramas.set(d.designacion, { clave: d.designacion, titulo: d.designacion, rotulo: TIPOS[d.tipo] ?? undefined, senales: [] });
  }
  const conductores: string[] = [];
  const maquina: string[] = [];
  const vistos = new Set<string>();
  for (const n of nombres) {
    if (!n || vistos.has(n)) continue;
    vistos.add(n);
    const des = designacionDe(n);
    if (des) {
      if (!ramas.has(des)) ramas.set(des, { clave: des, titulo: des, rotulo: /^-W/i.test(des) ? "Cable" : undefined, senales: [] });
      ramas.get(des)!.senales.push(n);
    } else if (CONDUCTOR.test(n)) conductores.push(n);
    else maquina.push(n);
  }
  const out = [...ramas.values()].filter((r) => r.senales.length);
  if (conductores.length) out.push({ clave: "#conductores", titulo: "Conductores", senales: conductores });
  if (maquina.length) out.push({ clave: "#maquina", titulo: "Máquina", senales: maquina });
  return out;
}

/** Filtra el árbol por un texto (sin distinguir mayúsculas): una rama cuyo título casa entra
 *  entera; si no, sólo sus señales que casan. */
export function filtrarArbol(ramas: readonly RamaSenales[], texto: string): RamaSenales[] {
  const q = texto.trim().toLowerCase();
  if (!q) return [...ramas];
  const out: RamaSenales[] = [];
  for (const r of ramas) {
    if (r.titulo.toLowerCase().includes(q) || (r.rotulo ?? "").toLowerCase().includes(q)) {
      out.push(r);
      continue;
    }
    const s = r.senales.filter((n) => n.toLowerCase().includes(q));
    if (s.length) out.push({ ...r, senales: s });
  }
  return out;
}
