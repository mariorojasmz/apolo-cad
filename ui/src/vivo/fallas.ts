import type { AparatoFallas, FallaCatalogo, InicioVivo, RamaVivo } from "./protocolo";

/* «Simular falla» en la sesión viva (plan cosim-fallas D7), la parte pura: los rótulos de cada
   falla para la persona, los campos que pide su valor, el evento que se manda por el WebSocket
   y las fallas activas (de `<des>.averia` en `textos` y de las ramas confirmadas por su ack).
   La LISTA de lo que se puede hacer fallar sale siempre del `inicio` (D6), nunca de aquí: esto
   sólo le pone nombre. Sin WebSocket ni React (se prueba en node). */

/** El evento `falla` como lo lee `cosim/escenario.py::_falla` (sin hora: entra en vivo). */
export interface EventoFalla {
  tipo: "falla";
  dispositivo?: string;
  rama?: string;
  falla: string;
  valor?: unknown;
  quitar?: true;
}

/** A qué se le pone la falla: un aparato del `inicio.fallas` o una rama del `inicio.ramas`. */
export type Objetivo =
  | { clase: "dispositivo"; clave: string; designacion: string; tipo: string; fallas: FallaCatalogo[] }
  | { clase: "rama"; clave: string; id: string; tipo: string; fallas: FallaCatalogo[] };

/** Las dos fallas de una rama (D3); `pegado` pide cómo queda el contacto. */
const FALLAS_CONTACTO: FallaCatalogo[] = [
  { falla: "pegado", pide: "bool" },
  { falla: "abierto", pide: "" },
];
const FALLAS_CONDUCTOR: FallaCatalogo[] = [{ falla: "abierto", pide: "" }];

/** Los aparatos y las ramas que se pueden hacer fallar, en el orden del `inicio`. */
export function objetivosDe(inicio: Pick<InicioVivo, "fallas" | "ramas">): Objetivo[] {
  const aparatos: Objetivo[] = (inicio.fallas ?? []).filter((a) => a.fallas.length).map((a: AparatoFallas) => ({
    clase: "dispositivo", clave: `d:${a.designacion}`, designacion: a.designacion, tipo: a.tipo, fallas: a.fallas,
  }));
  const ramas: Objetivo[] = (inicio.ramas ?? []).map((r: RamaVivo) => ({
    clase: "rama", clave: `r:${r.id}`, id: r.id, tipo: r.tipo,
    fallas: r.tipo === "contacto" ? FALLAS_CONTACTO : FALLAS_CONDUCTOR,
  }));
  return [...aparatos, ...ramas];
}

// ── nombres ──────────────────────────────────────────────────────────────────────────────────

const TIPOS: Record<string, string> = {
  contactor: "Contactor", rele: "Relé", pulsador: "Pulsador", seta: "Seta de emergencia",
  selector: "Selector", seccionador: "Seccionador", sensor: "Sensor", piloto: "Piloto",
  itm: "Interruptor termomagnético", guardamotor: "Guardamotor", rele_termico: "Relé térmico",
  fusible: "Fusible", plc: "PLC", variador: "Variador", fuente: "Fuente",
  resguardo: "Interruptor de resguardo", rele_seguridad: "Relé de seguridad",
  diferencial: "Interruptor diferencial",
  contacto: "Contacto", conductor: "Cable",
};

/** El nombre del tipo de aparato o de rama, para la lista. */
export function nombreTipoFalla(tipo: string): string {
  return TIPOS[tipo] ?? "Aparato";
}

/** Rótulo de la opción y frase para la barra («contacto soldado»), por falla y tipo. */
interface Nombre { rotulo: string; frase: (arg?: string) => string }

const PROTECCIONES = new Set(["itm", "guardamotor", "rele_termico", "fusible", "diferencial"]);

function nombreDe(falla: string, tipo: string, clase: Objetivo["clase"]): Nombre {
  if (clase === "rama") {
    if (falla === "pegado") return { rotulo: "Contacto pegado", frase: () => "contacto pegado" };
    if (falla === "abierto") {
      return tipo === "conductor"
        ? { rotulo: "Cable cortado", frase: () => "cable cortado" }
        : { rotulo: "Contacto que no cierra", frase: () => "contacto que no cierra" };
    }
  }
  switch (falla) {
    case "soldado":
      return { rotulo: "Contacto soldado", frase: () => "contacto soldado" };
    case "no_cierra":
      return { rotulo: "No cierra", frase: () => "bobina que no cierra" };
    case "trabado":
      return { rotulo: "Mecanismo trabado", frase: () => (tipo === "resguardo" ? "interruptor trabado" : "mando trabado") };
    case "pegado":
      return { rotulo: "Detección pegada", frase: () => "sensor pegado" };
    case "sin_salida":
      return tipo === "fuente"
        ? { rotulo: "Sin tensión de salida", frase: () => "fuente sin salida" }
        : { rotulo: "Sin salida", frase: () => "sensor sin salida" };
    case "no_dispara":
      return { rotulo: "No dispara", frase: () => "protección que no dispara" };
    case "abierto":
      if (tipo === "fusible") {
        return { rotulo: "Fundido", frase: (u) => (u ? `fusible ${u} fundido` : "fusible fundido") };
      }
      return { rotulo: "Se dispara sola", frase: () => (PROTECCIONES.has(tipo) ? "protección disparada sola" : "abierto solo") };
    case "entrada_pegada":
      return { rotulo: "Entrada pegada", frase: (b) => (b ? `entrada ${b} pegada` : "entrada pegada") };
    case "salida_pegada":
      if (tipo === "rele_seguridad") {
        return { rotulo: "Salida de seguridad soldada",
          frase: (s) => (s ? `salida de seguridad ${s} soldada` : "salida de seguridad soldada") };
      }
      return { rotulo: "Salida pegada", frase: (b) => (b ? `salida ${b} pegada` : "salida pegada") };
    case "detenido":
      return { rotulo: "Detenido, con las salidas en cero", frase: () => (tipo === "rele_seguridad" ? "relé detenido" : "PLC detenido") };
    case "canal_sto_pegado":
      return { rotulo: "Canal del STO pegado", frase: (c) => (c ? `canal ${c} del STO pegado` : "canal del STO pegado") };
    case "falla_interna":
      return { rotulo: "Falla interna", frase: () => "falla interna" };
    case "fundido":
      return { rotulo: "Lámpara fundida", frase: () => "lámpara fundida" };
    default: {
      // una falla que la UI todavía no nombra: su nombre interno, legible
      const t = falla.replace(/_/g, " ");
      return { rotulo: t.charAt(0).toUpperCase() + t.slice(1), frase: (a) => (a ? `${t} ${a}` : t) };
    }
  }
}

export function rotuloFalla(o: Objetivo, falla: string): string {
  return nombreDe(falla, o.tipo, o.clase).rotulo;
}

// ── el valor que pide cada falla ─────────────────────────────────────────────────────────────

export interface OpcionCampo {
  clave: string;
  rotulo: string;
}

/** Un campo del valor: una lista (la primera opción es la de por defecto) o una cuenta. */
export type Campo =
  | { id: string; rotulo: string; tipo: "lista"; opciones: OpcionCampo[] }
  | { id: string; rotulo: string; tipo: "numero"; min: number; paso: number };

/** Lo elegido en los campos, por `id` (las claves de las opciones o el número como texto). */
export type Elegido = Record<string, string>;

/** Una entrada analógica del PLC (`AI0`…): pegada, lleva su cuenta y no un nivel. */
export const esAnalogica = (borne: string) => /^AI\d/.test(borne);

const COMO_ESTA: OpcionCampo = { clave: "", rotulo: "Como está ahora" };

function estadosMando(tipo: string): [string, string] {
  switch (tipo) {
    case "seta":
      return ["Presionada", "Liberada"];
    case "seccionador":
      return ["Cerrado", "Abierto"];
    case "resguardo": // el valor es cómo quedan sus contactos (`cosim/modelos/seguridad.py`)
      return ["Contactos cerrados", "Contactos abiertos"];
    default:
      return ["Apretado", "Suelto"];
  }
}

/** Los campos que pide el valor de la falla `f` sobre `o` (vacío: no pide nada). */
export function camposDe(o: Objetivo, f: FallaCatalogo, elegido: Elegido = {}): Campo[] {
  const ops = (f.opciones ?? []).map(String);
  if (o.clase === "rama") {
    return f.falla === "pegado"
      ? [{ id: "valor", rotulo: "Queda", tipo: "lista", opciones: [{ clave: "1", rotulo: "Cerrado" }, { clave: "0", rotulo: "Abierto" }] }]
      : [];
  }
  switch (f.pide) {
    case "bool":
      return [{ id: "valor", rotulo: "Queda", tipo: "lista", opciones: [
        { clave: "1", rotulo: "Detectando siempre" }, { clave: "0", rotulo: "Sin detectar nunca" }] }];
    case "bool?": {
      const [si, no] = estadosMando(o.tipo);
      return [{ id: "valor", rotulo: "Queda", tipo: "lista", opciones: [COMO_ESTA, { clave: "1", rotulo: si }, { clave: "0", rotulo: no }] }];
    }
    case "posicion?":
      return [{ id: "valor", rotulo: "Queda en", tipo: "lista", opciones: [COMO_ESTA, ...ops.map((p) => ({ clave: p, rotulo: p }))] }];
    case "unidad?":
      return [{ id: "valor", rotulo: "Unidad", tipo: "lista", opciones: [
        { clave: "", rotulo: "Todas" }, ...ops.map((u) => ({ clave: u, rotulo: `Unidad ${u}` }))] }];
    case "canal":
      return [{ id: "valor", rotulo: "Canal", tipo: "lista", opciones: ops.map((c) => ({ clave: c, rotulo: c })) }];
    case "salida": // un NA de seguridad del relé, por sus bornes («13-14»)
      return [{ id: "valor", rotulo: "Salida", tipo: "lista", opciones: ops.map((s) => ({ clave: s, rotulo: `Bornes ${s}` })) }];
    case "borne,valor": {
      const borne = elegido.borne ?? ops[0] ?? "";
      const campos: Campo[] = [{ id: "borne", rotulo: "Borne", tipo: "lista", opciones: ops.map((b) => ({ clave: b, rotulo: b })) }];
      campos.push(esAnalogica(borne)
        ? { id: "cuenta", rotulo: "Cuenta", tipo: "numero", min: 0, paso: 1 }
        : { id: "valor", rotulo: "Queda", tipo: "lista", opciones: [{ clave: "1", rotulo: "Encendida" }, { clave: "0", rotulo: "Apagada" }] });
      return campos;
    }
    default:
      return [];
  }
}

/** Lo elegido por defecto: la primera opción de cada lista, 0 en una cuenta. */
export function elegidoInicial(o: Objetivo, f: FallaCatalogo): Elegido {
  const out: Elegido = {};
  for (const c of camposDe(o, f)) out[c.id] = c.tipo === "lista" ? c.opciones[0]?.clave ?? "" : "0";
  return out;
}

/** El `valor` del evento a partir de lo elegido; `undefined` = no lleva. */
export function valorDe(o: Objetivo, f: FallaCatalogo, elegido: Elegido): unknown {
  const e = { ...elegidoInicial(o, f), ...elegido };
  if (o.clase === "rama") return f.falla === "pegado" ? e.valor !== "0" : undefined;
  switch (f.pide) {
    case "bool":
      return e.valor !== "0";
    case "bool?":
      return e.valor === "" ? undefined : e.valor === "1";
    case "posicion?":
    case "canal":
    case "salida":
      return e.valor === "" ? undefined : e.valor;
    case "unidad?":
      return e.valor === "" ? undefined : Number(e.valor);
    case "borne,valor": {
      const borne = e.borne;
      if (!borne) return undefined;
      if (esAnalogica(borne)) return { borne, valor: Math.max(0, Math.round(Number(e.cuenta) || 0)) };
      return { borne, valor: e.valor !== "0" };
    }
    default:
      return undefined;
  }
}

/** El evento que pone la falla `f` en `o` con lo elegido. */
export function armarFalla(o: Objetivo, f: FallaCatalogo, elegido: Elegido = {}): EventoFalla {
  const ev: EventoFalla = o.clase === "dispositivo"
    ? { tipo: "falla", dispositivo: o.designacion, falla: f.falla }
    : { tipo: "falla", rama: o.id, falla: f.falla };
  const v = valorDe(o, f, elegido);
  if (v !== undefined) ev.valor = v;
  return ev;
}

// ── las activas ──────────────────────────────────────────────────────────────────────────────

export interface FallaActiva {
  /** Única en la lista: «-K1|soldado», «-A1|entrada_pegada I0.0», «r:-K1:13-14|pegado». */
  clave: string;
  /** «contacto soldado en -K1». */
  frase: string;
  /** Las dos partes de la frase: qué falla («contacto soldado») y dónde («-K1»). */
  que: string;
  donde: string;
  /** El evento que la quita (`quitar: true`). */
  quitar: EventoFalla;
}

/** El valor que identifica una de varias fallas del mismo nombre al quitarla (su etiqueta). */
function valorParaQuitar(falla: string, arg: string | undefined, tipo: string): unknown {
  if (!arg) return undefined;
  if (falla === "salida_pegada" && tipo === "rele_seguridad") return arg; // la salida, «13-14»
  if (falla === "entrada_pegada" || falla === "salida_pegada") return { borne: arg };
  if (falla === "canal_sto_pegado") return arg;
  if (falla === "abierto" && /^\d+$/.test(arg)) return Number(arg);
  return undefined;
}

/** Las fallas de los aparatos que publican `<des>.averia` (texto: etiquetas separadas por «, »,
 *  como las arma `Modelo.averia`) y las de rama confirmadas, en ese orden. */
export function activasDe(
  textos: Record<string, string>,
  inicio: Pick<InicioVivo, "fallas" | "ramas"> | null,
  ramas: readonly EventoFalla[] = [],
): FallaActiva[] {
  const tipos = new Map((inicio?.fallas ?? []).map((a) => [a.designacion, a.tipo]));
  const tiposRama = new Map((inicio?.ramas ?? []).map((r) => [r.id, r.tipo]));
  const out: FallaActiva[] = [];
  for (const [senal, texto] of Object.entries(textos)) {
    if (!senal.endsWith(".averia") || !texto) continue;
    const des = senal.slice(0, -".averia".length);
    const tipo = tipos.get(des) ?? "";
    for (const etiqueta of texto.split(", ")) {
      const [falla, ...resto] = etiqueta.trim().split(" ");
      if (!falla) continue;
      const arg = resto.join(" ") || undefined;
      const quitar: EventoFalla = { tipo: "falla", dispositivo: des, falla, quitar: true };
      const v = valorParaQuitar(falla, arg, tipo);
      if (v !== undefined) quitar.valor = v;
      const que = nombreDe(falla, tipo, "dispositivo").frase(arg);
      out.push({ clave: `${des}|${etiqueta}`, frase: `${que} en ${des}`, que, donde: des, quitar });
    }
  }
  for (const r of ramas) {
    if (!r.rama) continue;
    const tipo = tiposRama.get(r.rama) ?? "contacto";
    const base = nombreDe(r.falla, tipo, "rama").frase();
    const como = r.falla === "pegado" ? (r.valor === false ? " abierto" : " cerrado") : "";
    out.push({ clave: `r:${r.rama}|${r.falla}`, frase: `${base}${como} en ${r.rama}`, que: `${base}${como}`, donde: r.rama,
      quitar: { tipo: "falla", rama: r.rama, falla: r.falla, quitar: true } });
  }
  return out;
}

/** Las fallas de rama no publican `averia` (son de la red, no de un aparato): la UI las lleva
 *  por el ack de su evento. Devuelve la lista nueva (o la misma si el ack no es de una rama). */
export function conAckDeRama(ramas: readonly EventoFalla[], evento: unknown): readonly EventoFalla[] {
  if (!evento || typeof evento !== "object") return ramas;
  const e = evento as Partial<EventoFalla>;
  if (e.tipo !== "falla" || typeof e.rama !== "string" || typeof e.falla !== "string") return ramas;
  const otras = ramas.filter((r) => !(r.rama === e.rama && r.falla === e.falla));
  if (e.quitar) return otras;
  const nueva: EventoFalla = { tipo: "falla", rama: e.rama, falla: e.falla };
  if (e.valor !== undefined) nueva.valor = e.valor;
  return [...otras, nueva];
}

/** Lo que distingue una de varias fallas del mismo nombre en un aparato: el borne, el canal, la
 *  salida del relé o la unidad (undefined si no hay nada que distinguir). */
function identidad(falla: string, valor: unknown): string | undefined {
  if (valor && typeof valor === "object" && "borne" in valor) return String((valor as { borne: unknown }).borne);
  if ((falla === "canal_sto_pegado" || falla === "salida_pegada") && typeof valor === "string") return valor;
  if (falla === "abierto" && typeof valor === "number") return String(valor);
  return undefined;
}

/** La activa que el evento `ev` volvería a poner (para que el botón ofrezca quitarla). */
export function activaIgual(activas: readonly FallaActiva[], ev: EventoFalla): FallaActiva | undefined {
  const id = identidad(ev.falla, ev.valor);
  return activas.find((a) => a.quitar.falla === ev.falla
    && (ev.dispositivo !== undefined ? a.quitar.dispositivo === ev.dispositivo : a.quitar.rama === ev.rama)
    && identidad(a.quitar.falla, a.quitar.valor) === id);
}

/** Lo que dice la barra: «Falla activa: …» con una, «3 fallas activas» con varias. */
export function resumenActivas(activas: readonly FallaActiva[]): string {
  if (!activas.length) return "";
  if (activas.length === 1) return `Falla activa: ${activas[0].frase}`;
  return `${activas.length} fallas activas`;
}
