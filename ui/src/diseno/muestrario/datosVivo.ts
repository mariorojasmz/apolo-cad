import { useVivo } from "../../vivo/estado";
import { conAckDeRama, type EventoFalla } from "../../vivo/fallas";
import type { Accion } from "../../vivo/mandos";
import type { InicioVivo, MandoVivo } from "../../vivo/protocolo";

/* Datos de EJEMPLO de la sesión viva para el muestrario (plan cosim-fallas D7): un `inicio` con
   la forma de `cosim/fallas.py::catalogo` (contactor, seta, sensor, PLC, variador, protecciones,
   el resguardo y el relé de seguridad, contactos y un cable) y lo que el servidor contestaría a
   una falla o a un mando, para revisar «Mandos», «Simular falla» y la barra sin API.
   `?fallas=0|1|3` elige con cuántas activas arranca. */

const B2: MandoVivo = { designacion: "-B2", tipo: "resguardo", ref: "RESG-2NC", acciones: ["abrir", "cerrar"],
  color: null, senales: ["-B2.cerrado"] };

export const INICIO_DEMO: InicioVivo = {
  tipo: "inicio", version: 1, proyecto: null, escenario: "marcha", firma: "demo", ventana_s: 60, max_s: 600,
  ritmo: 1, dt_s: 0.001, formato: 1, cuerpos: [], productos: [], juntas: [], bandas: [], senales: [],
  mandos: [
    { designacion: "-S0", tipo: "seta", ref: "ESTOP-40-2NC", acciones: ["presionar", "liberar"], color: "rojo",
      fondo: "amarillo", senales: ["-S0.accionado"] },
    B2,
    { designacion: "-S3", tipo: "pulsador", ref: "PULS-22-AZUL-NA", acciones: ["pulsar", "soltar"], color: "azul", // voseo-interno
      retorno: "resorte", actuadores: ["mano"], potenciometro: false, senales: ["-S3.accionado"] },
  ],
  pilotos: [],
  dispositivos: [
    { designacion: "-K2", tipo: "rele_seguridad", ref: "RS-2C-24VDC" },
    { designacion: "-M1", tipo: "motor", ref: "NMRV-090" },
    // el PLC y el panel de operador de la pantalla 3D de prueba (plan plc-en-el-lazo D13)
    { designacion: "-K1", tipo: "plc", ref: "PLC-1214C-DC" },
    { designacion: "-P1", tipo: "hmi", ref: "HMI-7IN-24VDC", pieza: "panel-operador", pantalla_px: [800, 480] },
  ],
  fajas: [], cadenas: [], avisos: [],
  fallas: [
    { designacion: "-K1", tipo: "contactor", fallas: [{ falla: "soldado", pide: "" }, { falla: "no_cierra", pide: "" }] },
    { designacion: "-S0", tipo: "seta", fallas: [{ falla: "trabado", pide: "bool?" }] },
    { designacion: "-S1", tipo: "pulsador", fallas: [{ falla: "trabado", pide: "bool?" }] },
    { designacion: "-B1", tipo: "sensor", fallas: [{ falla: "pegado", pide: "bool" }, { falla: "sin_salida", pide: "" }] },
    { designacion: "-A1", tipo: "plc", fallas: [
      { falla: "entrada_pegada", pide: "borne,valor", opciones: ["I0.0", "I0.1", "I0.2", "I0.3", "AI0"] },
      { falla: "salida_pegada", pide: "borne,valor", opciones: ["Q0.0", "Q0.1"] },
      { falla: "detenido", pide: "" }] },
    { designacion: "-T1", tipo: "variador", fallas: [
      { falla: "canal_sto_pegado", pide: "canal", opciones: ["S1", "S2"] }, { falla: "falla_interna", pide: "" }] },
    { designacion: "-Q1", tipo: "guardamotor", fallas: [{ falla: "no_dispara", pide: "" }, { falla: "abierto", pide: "" }] },
    { designacion: "-G1", tipo: "fuente", fallas: [{ falla: "sin_salida", pide: "" }] },
    { designacion: "-H1", tipo: "piloto", fallas: [{ falla: "fundido", pide: "" }] },
    { designacion: "-B2", tipo: "resguardo", fallas: [{ falla: "trabado", pide: "bool?" }] },
    { designacion: "-K2", tipo: "rele_seguridad", fallas: [
      { falla: "salida_pegada", pide: "salida", opciones: ["13-14", "23-24", "33-34"] }, { falla: "detenido", pide: "" }] },
  ],
  ramas: [
    { id: "-K1:13-14", tipo: "contacto", red: "mando", dispositivo: "-K1" },
    { id: "-S0:11-12", tipo: "contacto", red: "mando", dispositivo: "-S0" },
    { id: "-S0:21-22", tipo: "contacto", red: "mando", dispositivo: "-S0" },
    { id: "-B2:11-12", tipo: "contacto", red: "mando", dispositivo: "-B2" },
    { id: "-B2:21-22", tipo: "contacto", red: "mando", dispositivo: "-B2" },
    { id: "-W3", tipo: "conductor", red: "potencia" },
  ],
};

/** La etiqueta que `Modelo.averia` daría a la falla (`cosim/modelos`). */
function etiqueta(ev: EventoFalla): string {
  const v = ev.valor;
  if (v && typeof v === "object" && "borne" in v) return `${ev.falla} ${(v as { borne: string }).borne}`;
  if ((ev.falla === "canal_sto_pegado" || ev.falla === "salida_pegada") && typeof v === "string") return `${ev.falla} ${v}`;
  return ev.falla;
}

/* El resguardo y el relé de seguridad como los modela `cosim/modelos/seguridad.py`, en corto:
   abrir abre los dos canales (salvo el contacto pegado) y las salidas; el relé rearma al SOLTAR
   -S3 con los dos canales cerrados, si los dos abrieron y cerraron y no tiene una falla. */
const LECTURAS_DEMO: Record<string, number> = {
  "-S0.accionado": 0, "-B2.cerrado": 1, "-S3.accionado": 0, "-M1.rpm": 1799, "-M1.I_A": 3.8,
  "-K2.salidas": 1, "-K2.canal1": 1, "-K2.canal2": 1, "-K2.espera_ciclo": 0, "-K1.Main.consigna": 50,
};

function pegada(rama: string): boolean {
  return useVivo.getState().ramasEnFalla.some((r) => r.rama === rama && r.falla === "pegado" && r.valor !== false);
}

/** Lo que haría la sesión con la acción de un mando del muestrario. */
export function accionarLocal(a: Accion, m: MandoVivo): void {
  const st = useVivo.getState();
  const l = { ...st.lecturas };
  const des = m.designacion;
  if (a.accion === "presionar" || a.accion === "liberar") l[`${des}.accionado`] = a.accion === "presionar" ? 1 : 0;
  if (m.tipo === "resguardo" && (a.accion === "abrir" || a.accion === "cerrar")) {
    const cierra = a.accion === "cerrar";
    l["-B2.cerrado"] = cierra ? 1 : 0;
    l["-K2.canal1"] = cierra || pegada("-B2:11-12") ? 1 : 0;
    l["-K2.canal2"] = cierra || pegada("-B2:21-22") ? 1 : 0;
    if (!cierra) l["-K2.salidas"] = 0;
    l["-K2.espera_ciclo"] = cierra ? (pegada("-B2:11-12") || pegada("-B2:21-22") ? 1 : 0) : 1;
  }
  if (a.accion === "pulsar") l[`${des}.accionado`] = 1; // voseo-interno
  if (a.accion === "soltar") {
    l[`${des}.accionado`] = 0;
    const averia = st.textos["-K2.averia"] ?? "";
    if (l["-K2.canal1"] && l["-K2.canal2"] && !l["-K2.espera_ciclo"] && !averia) l["-K2.salidas"] = 1;
  }
  l["-M1.rpm"] = l["-K2.salidas"] && !l["-S0.accionado"] ? 1799 : 0;
  l["-M1.I_A"] = l["-M1.rpm"] ? 3.8 : 0;
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

/** Arranca la sesión de ejemplo con 0, 1 o 3 fallas activas. */
export function prepararSesionDemo(activas: number): void {
  useVivo.getState().set({ fase: "corriendo", escenario: "marcha", inicio: INICIO_DEMO, t: 12.4, textos: {}, ramasEnFalla: [],
    lecturas: { ...LECTURAS_DEMO }, esperadas: {} });
  const iniciales: EventoFalla[] = [
    { tipo: "falla", dispositivo: "-K1", falla: "soldado" },
    { tipo: "falla", rama: "-S0:11-12", falla: "pegado", valor: true },
    { tipo: "falla", dispositivo: "-A1", falla: "salida_pegada", valor: { borne: "Q0.1", valor: true } },
  ];
  iniciales.slice(0, activas).forEach(simularLocal);
}
