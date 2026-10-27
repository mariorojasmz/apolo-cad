import { useVivo } from "../../vivo/estado";
import { conAckDeRama, type EventoFalla } from "../../vivo/fallas";
import type { Accion } from "../../vivo/mandos";
import type { InicioVivo, MandoVivo } from "../../vivo/protocolo";

/* Datos de EJEMPLO de la sesión viva para el muestrario: la mezcladora de paletas de 200 L (plan
   nombres-por-funcion F3; rótulos del informe § 3.2) con sus 8 mandos, 4 pilotos y 2 relés de
   seguridad, los nombres como los suma la API al `inicio` (`services/nombres_aparatos.py`: rótulo,
   origen, grupo, estados, descripción, rearme), las fallas de `cosim/fallas.py::catalogo` y lo
   que el servidor contestaría a una falla o a un mando, para revisar «Mandos», «Simular falla» y
   la barra sin API. `?fallas=0|1|3` elige con cuántas activas arranca; `?mandos=` el estado:
   `rearmar` (por defecto: la seguridad sin rearmar), `marcha`, `sin-energia`, `seta`, `tapa`. */

const pieza = (des: string) => `c400_d_${des}`;
const RESGUARDO: Pick<MandoVivo, "tipo" | "ref" | "acciones" | "color"> = {
  tipo: "resguardo", ref: "RESG-2NC", acciones: ["abrir", "cerrar"], color: null };
const PULSADOR: Pick<MandoVivo, "tipo" | "acciones" | "retorno" | "actuadores" | "potenciometro"> = {
  tipo: "pulsador", acciones: ["pulsar", "soltar"], retorno: "resorte", actuadores: ["mano"], potenciometro: false }; // voseo-interno

const MANDOS: MandoVivo[] = [
  { designacion: "-Q1", tipo: "seccionador", ref: "SECC-3P-25A", acciones: ["abrir", "cerrar"], color: null,
    pieza: pieza("-Q1"), senales: ["-Q1.cerrado"], rotulo: "Interruptor general", origen: "tipo", grupo: "energia",
    estados: { cerrado: "Encendido", abierto: "Apagado" } },
  { designacion: "-S0", tipo: "seta", ref: "ESTOP-40-2NC", acciones: ["presionar", "liberar"], color: "rojo",
    fondo: "amarillo", pieza: pieza("-S0"), senales: ["-S0.accionado"], rotulo: "Parada de emergencia", origen: "tipo",
    grupo: "seguridad" },
  { ...PULSADOR, designacion: "-S1", ref: "PULS-22-VERDE-NA", color: "verde", pieza: pieza("-S1"), senales: ["-S1.accionado"],
    rotulo: "Marcha", origen: "declarado", grupo: "operacion" },
  { ...PULSADOR, designacion: "-S2", ref: "PULS-22-ROJO-NC", color: "rojo", pieza: pieza("-S2"), senales: ["-S2.accionado"],
    rotulo: "Paro", origen: "declarado", grupo: "operacion",
    descripcion: "Para el motor de mezcla al terminar la vuelta. No corta la energía: para eso está la parada de emergencia." },
  { ...PULSADOR, designacion: "-S3", ref: "PULS-22-AZUL-NA", color: "azul", pieza: pieza("-S3"), senales: ["-S3.accionado"],
    rotulo: "Rearme de seguridad", origen: "declarado", grupo: "seguridad", rearma: ["-K2", "-K3"],
    descripcion: "Rearma los dos relés de seguridad. Sólo rearma con la tapa cerrada, el recipiente acoplado y la parada de emergencia liberada." },
  { designacion: "-S4", tipo: "selector", ref: "SEL-22-2P", acciones: ["girar"], color: "negro", pieza: pieza("-S4"),
    posiciones: ["0", "I"], senales: [], rotulo: "Modo", origen: "declarado", grupo: "operacion",
    estados: { 0: "Manual", I: "Ciclo" } },
  { ...RESGUARDO, designacion: "-B1", pieza: "c66", senales: ["-B1.cerrado"], rotulo: "Tapa del tanque", origen: "declarado",
    grupo: "seguridad", estados: { cerrado: "Cerrada", abierto: "Abierta" } },
  { ...RESGUARDO, designacion: "-B4", pieza: "c361", senales: ["-B4.cerrado"], rotulo: "Recipiente bajo la descarga",
    origen: "declarado", grupo: "seguridad", estados: { cerrado: "Acoplado", abierto: "Sin recipiente" } },
];

const piloto = (des: string, color: string, rotulo: string) =>
  ({ designacion: des, ref: `PIL-22-${color.toUpperCase()}`, color, pieza: pieza(des), senal: `${des}.encendido`, rotulo,
    origen: "declarado", grupo: "pilotos" });
const PILOTOS = [piloto("-P1", "verde", "Marcha"), piloto("-P2", "rojo", "Falla"), piloto("-P3", "ambar", "Tapa abierta"),
  piloto("-P4", "ambar", "Recipiente no acoplado")];

/** Como en el servidor, `dispositivos` lleva TODOS los aparatos (también mandos y pilotos), cada
 *  uno con su nombre: de ahí titula «Señales». */
const comoDispositivo = ({ designacion, ref, pieza: p, rotulo, origen, grupo, ...x }: MandoVivo | ReturnType<typeof piloto>) =>
  ({ designacion, tipo: "tipo" in x ? x.tipo : "piloto", ref, pieza: p, rotulo, origen, grupo });

export const INICIO_DEMO: InicioVivo = {
  tipo: "inicio", version: 1, proyecto: null, escenario: "ciclo_nominal", titulo_escenario: "Ciclo nominal", firma: "demo",
  ventana_s: 60, max_s: 600, ritmo: 1, dt_s: 0.001, formato: 1, cuerpos: [], productos: [], bandas: [], senales: [],
  // las juntas por su pieza hija (nombres-por-funcion D15): el `nombre` lo suma la API
  juntas: [
    { name: "j_eje_paletas", tipo: "continua", unidad: "grados", nombre: "Eje de paletas" },
    { name: "j_tapa_carga", tipo: "giratoria", unidad: "grados", nombre: "Tapa de carga" },
    { name: "c388_puerta", tipo: "giratoria", unidad: "grados", nombre: "Puerta del tablero" },
  ],
  // la válvula de la compuerta con su accionamiento manual y el nombre de cada posición (A4)
  valvulas: [{ designacion: "-QM1", ref: "VAL-52-MONO-G18", lados: ["14"], manual: true, pieza: "c70_valvula",
    rotulo: "Válvula de la compuerta", origen: "declarado", grupo: "operacion", posiciones: ["14", "12"],
    estados: { 14: "Compuerta abierta", 12: "Compuerta cerrada" } }],
  mandos: MANDOS,
  pilotos: PILOTOS,
  dispositivos: [
    ...MANDOS.map(comoDispositivo), ...PILOTOS.map(comoDispositivo),
    { designacion: "-M1", tipo: "motor", ref: "MOTOR-1.5KW-4P", rotulo: "Motor de mezcla", origen: "pieza", grupo: "lecturas" },
    { designacion: "-K2", tipo: "rele_seguridad", ref: "RS-2C-24VDC", rotulo: "Seguridad de parada de emergencia y tapa del tanque",
      origen: "derivado", grupo: "lecturas" },
    { designacion: "-K3", tipo: "rele_seguridad", ref: "RS-2C-24VDC", rotulo: "Seguridad de recipiente bajo la descarga",
      origen: "derivado", grupo: "lecturas" },
    // el PLC y el panel de operador de la pantalla 3D de prueba (plan plc-en-el-lazo D13)
    { designacion: "-K1", tipo: "plc", ref: "PLC-1214C-DC", rotulo: "PLC", origen: "tipo", grupo: "lecturas" },
    { designacion: "-A2", tipo: "hmi", ref: "HMI-7IN-24VDC", pieza: "panel-operador", pantalla_px: [800, 480],
      rotulo: "Panel de operador", origen: "tipo", grupo: "lecturas" },
    // el aire de la compuerta (V8.9): la válvula y el cilindro, por lo que hacen
    { designacion: "-QM1", tipo: "electrovalvula", ref: "VAL-52-MONO-G18", pieza: "c70_valvula",
      rotulo: "Válvula de la compuerta", origen: "declarado", grupo: "operacion" },
    { designacion: "-MM1", tipo: "cilindro", ref: "CIL-ISO15552-32", pieza: "c68_cuerpo", carrera_mm: 200,
      rotulo: "Cilindro de compuerta", origen: "declarado", grupo: "lecturas" },
  ],
  fajas: [], cadenas: [], avisos: [],
  fallas: [
    { designacion: "-KM1", tipo: "contactor", rotulo: "Contactor", origen: "tipo",
      fallas: [{ falla: "soldado", pide: "" }, { falla: "no_cierra", pide: "" }] },
    { designacion: "-Q1", tipo: "seccionador", rotulo: "Interruptor general", origen: "tipo", fallas: [{ falla: "trabado", pide: "bool?" }] },
    { designacion: "-S0", tipo: "seta", rotulo: "Parada de emergencia", origen: "tipo", fallas: [{ falla: "trabado", pide: "bool?" }] },
    { designacion: "-S1", tipo: "pulsador", rotulo: "Marcha", origen: "declarado", fallas: [{ falla: "trabado", pide: "bool?" }] },
    { designacion: "-B1", tipo: "resguardo", rotulo: "Tapa del tanque", origen: "declarado", fallas: [{ falla: "trabado", pide: "bool?" }] },
    { designacion: "-K1", tipo: "plc", rotulo: "PLC", origen: "tipo", fallas: [
      { falla: "entrada_pegada", pide: "borne,valor", opciones: ["I0.0", "I0.1", "I0.2", "I0.3", "AI0"] },
      { falla: "salida_pegada", pide: "borne,valor", opciones: ["Q0.0", "Q0.1"] },
      { falla: "detenido", pide: "" }] },
    { designacion: "-Q2", tipo: "guardamotor", rotulo: "Guardamotor", origen: "tipo",
      fallas: [{ falla: "no_dispara", pide: "" }, { falla: "abierto", pide: "" }] },
    { designacion: "-G1", tipo: "fuente", rotulo: "Fuente", origen: "tipo", fallas: [{ falla: "sin_salida", pide: "" }] },
    { designacion: "-P2", tipo: "piloto", rotulo: "Falla", origen: "declarado", fallas: [{ falla: "fundido", pide: "" }] },
    { designacion: "-K2", tipo: "rele_seguridad", rotulo: "Seguridad de parada de emergencia y tapa del tanque", origen: "derivado",
      fallas: [{ falla: "salida_pegada", pide: "salida", opciones: ["13-14", "23-24", "33-34"] }, { falla: "detenido", pide: "" }] },
    { designacion: "-K3", tipo: "rele_seguridad", rotulo: "Seguridad de recipiente bajo la descarga", origen: "derivado",
      fallas: [{ falla: "salida_pegada", pide: "salida", opciones: ["13-14", "23-24", "33-34"] }, { falla: "detenido", pide: "" }] },
  ],
  ramas: [
    { id: "-KM1:13-14", tipo: "contacto", red: "mando", dispositivo: "-KM1", nombre: "Contacto 13-14 · Contactor" },
    { id: "-S0:11-12", tipo: "contacto", red: "mando", dispositivo: "-S0", nombre: "Contacto 11-12 · Parada de emergencia" },
    { id: "-S0:21-22", tipo: "contacto", red: "mando", dispositivo: "-S0", nombre: "Contacto 21-22 · Parada de emergencia" },
    { id: "-B1:11-12", tipo: "contacto", red: "mando", dispositivo: "-B1", nombre: "Contacto 11-12 · Tapa del tanque" },
    { id: "-B1:21-22", tipo: "contacto", red: "mando", dispositivo: "-B1", nombre: "Contacto 21-22 · Tapa del tanque" },
    { id: "-W1.1", tipo: "conductor", red: "potencia", nombre: "Cable Red de suministro → Interruptor general" },
  ],
};

/** La etiqueta que `Modelo.averia` daría a la falla (`cosim/modelos`). */
function etiqueta(ev: EventoFalla): string {
  const v = ev.valor;
  if (v && typeof v === "object" && "borne" in v) return `${ev.falla} ${(v as { borne: string }).borne}`;
  if ((ev.falla === "canal_sto_pegado" || ev.falla === "salida_pegada") && typeof v === "string") return `${ev.falla} ${v}`;
  return ev.falla;
}

/* La mezcladora como la modelan `cosim/modelos/seguridad.py` y su programa, en corto: -K2 vigila la
   seta y la tapa (canales 11-12 y 21-22), -K3 el recipiente; los dos rearman al SOLTAR -S3 con sus
   canales cerrados, si abrieron y cerraron y no tienen falla. Sin energía (-Q1 abierto) nada queda
   habilitado. «Marcha» arranca el motor con las dos seguridades habilitadas; «Paro» lo para. */
const BASE: Record<string, number> = {
  "-Q1.cerrado": 1, "-S0.accionado": 0, "-S1.accionado": 0, "-S2.accionado": 0, "-S3.accionado": 0,
  "-B1.cerrado": 1, "-B4.cerrado": 1, "-M1.rpm": 0, "-M1.I_A": 0,
  "-K2.salidas": 0, "-K2.canal1": 1, "-K2.canal2": 1, "-K2.espera_ciclo": 0,
  "-K3.salidas": 0, "-K3.canal1": 1, "-K3.canal2": 1, "-K3.espera_ciclo": 0,
  "-P1.encendido": 0, "-P2.encendido": 0, "-P3.encendido": 0, "-P4.encendido": 0, "-K1.Main.consigna": 50,
  "-QM1.bobina14": 0, "-MM1.x_mm": 200, "-MM1.pA_bar": 6, "-MM1.pB_bar": 0, "-W1.1.I_A": 0,
};
const PRESETS: Record<string, Record<string, number>> = {
  rearmar: {},
  marcha: { "-K2.salidas": 1, "-K3.salidas": 1, "-M1.rpm": 1450, "-M1.I_A": 2.9, "-P1.encendido": 1 },
  "sin-energia": { "-Q1.cerrado": 0 },
  seta: { "-S0.accionado": 1, "-K2.canal1": 0, "-K2.canal2": 0, "-K3.salidas": 1 },
  tapa: { "-B1.cerrado": 0, "-K2.canal1": 0, "-K2.canal2": 0, "-K3.salidas": 1, "-P3.encendido": 1 },
};

function pegada(rama: string): boolean {
  return useVivo.getState().ramasEnFalla.some((r) => r.rama === rama && r.falla === "pegado" && r.valor !== false);
}

/** Los canales de los dos relés según lo que está en serie con cada uno. */
function canales(l: Record<string, number>): void {
  const libre = !l["-S0.accionado"];
  const tapa = !!l["-B1.cerrado"];
  l["-K2.canal1"] = (libre || pegada("-S0:11-12")) && (tapa || pegada("-B1:11-12")) ? 1 : 0;
  l["-K2.canal2"] = (libre || pegada("-S0:21-22")) && (tapa || pegada("-B1:21-22")) ? 1 : 0;
  l["-K3.canal1"] = l["-K3.canal2"] = l["-B4.cerrado"] ? 1 : 0;
  for (const k of ["-K2", "-K3"]) {
    if (!l[`${k}.canal1`] || !l[`${k}.canal2`]) {
      l[`${k}.salidas`] = 0;
      if (!l[`${k}.canal1`] && !l[`${k}.canal2`]) l[`${k}.espera_ciclo`] = 0; // abrieron los dos: el ciclo vale
      else l[`${k}.espera_ciclo`] = 1;
    }
  }
}

/** Lo que haría la sesión con la acción de un mando del muestrario. */
export function accionarLocal(a: Accion, m: MandoVivo): void {
  const st = useVivo.getState();
  const l = { ...st.lecturas };
  const des = m.designacion;
  if (a.accion === "girar" && m.tipo === "selector") {
    st.set({ textos: { ...st.textos, [`${des}.posicion`]: String(a.valor) } });
    return;
  }
  if (a.accion === "presionar" || a.accion === "liberar") l[`${des}.accionado`] = a.accion === "presionar" ? 1 : 0;
  if (a.accion === "abrir" || a.accion === "cerrar") l[`${des}.cerrado`] = a.accion === "cerrar" ? 1 : 0;
  if (a.accion === "pulsar") l[`${des}.accionado`] = 1; // voseo-interno
  if (a.accion === "soltar") l[`${des}.accionado`] = 0;
  canales(l);
  const energia = !!l["-Q1.cerrado"];
  if (!energia) l["-K2.salidas"] = l["-K3.salidas"] = 0;
  if (a.accion === "soltar" && des === "-S3" && energia) {
    for (const k of ["-K2", "-K3"]) {
      const averia = st.textos[`${k}.averia`] ?? "";
      if (l[`${k}.canal1`] && l[`${k}.canal2`] && !l[`${k}.espera_ciclo`] && !averia) l[`${k}.salidas`] = 1;
    }
  }
  const habilitada = energia && l["-K2.salidas"] && l["-K3.salidas"];
  if (a.accion === "soltar" && des === "-S1" && habilitada) l["-M1.rpm"] = 1450;
  if ((a.accion === "pulsar" && des === "-S2") || !habilitada) l["-M1.rpm"] = 0; // voseo-interno
  l["-M1.I_A"] = l["-M1.rpm"] ? 2.9 : 0;
  l["-P1.encendido"] = l["-M1.rpm"] ? 1 : 0;
  l["-P3.encendido"] = l["-B1.cerrado"] ? 0 : 1;
  l["-P4.encendido"] = l["-B4.cerrado"] ? 0 : 1;
  st.set({ lecturas: l });
}

/** Lo que haría el servidor con la falla: la avería del aparato en `textos`, o el ack de rama. */
export function simularLocal(ev: EventoFalla): void {
  const st = useVivo.getState();
  if (ev.rama) {
    st.set({ ramasEnFalla: conAckDeRama(st.ramasEnFalla, ev) });
    return;
  }
  const senal = `${ev.dispositivo}.averia`;
  const antes = (st.textos[senal] ?? "").split(", ").filter(Boolean);
  const e = etiqueta(ev);
  const exacta = e !== ev.falla; // con borne o canal se quita esa; sin, todas las de ese nombre
  const despues = ev.quitar
    ? antes.filter((x) => (exacta ? x !== e : x.split(" ")[0] !== ev.falla))
    : antes.includes(e) ? antes : [...antes, e];
  st.set({ textos: { ...st.textos, [senal]: despues.join(", ") } });
}

/** Arranca la sesión de ejemplo con 0, 1 o 3 fallas activas y los mandos en el estado `mandos`. */
export function prepararSesionDemo(activas: number, mandos = "rearmar"): void {
  useVivo.getState().set({ fase: "corriendo", escenario: INICIO_DEMO.escenario, inicio: INICIO_DEMO, t: 12.4,
    textos: { "-S4.posicion": "I", "-QM1.posicion": "12", "-QM1.manual": "0" }, ramasEnFalla: [], lecturas: { ...BASE, ...(PRESETS[mandos] ?? {}) }, esperadas: {} });
  const iniciales: EventoFalla[] = [
    { tipo: "falla", dispositivo: "-KM1", falla: "soldado" },
    { tipo: "falla", rama: "-S0:11-12", falla: "pegado", valor: true },
    { tipo: "falla", dispositivo: "-K1", falla: "salida_pegada", valor: { borne: "Q0.1", valor: true } },
  ];
  iniciales.slice(0, activas).forEach(simularLocal);
}
