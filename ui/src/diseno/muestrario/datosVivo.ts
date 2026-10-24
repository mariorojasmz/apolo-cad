import { useVivo } from "../../vivo/estado";
import { conAckDeRama, type EventoFalla } from "../../vivo/fallas";
import type { InicioVivo } from "../../vivo/protocolo";

/* Datos de EJEMPLO de la sesión viva para el muestrario (plan cosim-fallas D7): un `inicio` con
   la forma de `cosim/fallas.py::catalogo` (contactor, seta, sensor, PLC, variador, protecciones,
   un contacto y un cable) y lo que el servidor contestaría a una falla, para revisar «Simular
   falla» y la barra sin API. `?fallas=0|1|3` elige con cuántas activas arranca. */

export const INICIO_DEMO: InicioVivo = {
  tipo: "inicio", version: 1, proyecto: null, escenario: "marcha", firma: "demo", ventana_s: 60, max_s: 600,
  ritmo: 1, dt_s: 0.001, formato: 1, cuerpos: [], productos: [], juntas: [], bandas: [], senales: [],
  mandos: [], pilotos: [], dispositivos: [], fajas: [], cadenas: [], avisos: [],
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
  ],
  ramas: [
    { id: "-K1:13-14", tipo: "contacto", red: "mando", dispositivo: "-K1" },
    { id: "-S0:11-12", tipo: "contacto", red: "mando", dispositivo: "-S0" },
    { id: "-S0:21-22", tipo: "contacto", red: "mando", dispositivo: "-S0" },
    { id: "-W3", tipo: "conductor", red: "potencia" },
  ],
};

/** La etiqueta que `Modelo.averia` daría a la falla (`cosim/modelos`). */
function etiqueta(ev: EventoFalla): string {
  const v = ev.valor;
  if (v && typeof v === "object" && "borne" in v) return `${ev.falla} ${(v as { borne: string }).borne}`;
  if (ev.falla === "canal_sto_pegado" && typeof v === "string") return `${ev.falla} ${v}`;
  return ev.falla;
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
  useVivo.getState().set({ fase: "corriendo", escenario: "marcha", inicio: INICIO_DEMO, t: 12.4, textos: {}, ramasEnFalla: [] });
  const iniciales: EventoFalla[] = [
    { tipo: "falla", dispositivo: "-K1", falla: "soldado" },
    { tipo: "falla", rama: "-S0:11-12", falla: "pegado", valor: true },
    { tipo: "falla", dispositivo: "-A1", falla: "salida_pegada", valor: { borne: "Q0.1", valor: true } },
  ];
  iniciales.slice(0, activas).forEach(simularLocal);
}
