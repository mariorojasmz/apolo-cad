import { useStore } from "../state/store";
import { useMarcha } from "../viewport/marcha/estado";
import { INICIAL, useVivo } from "./estado";
import { esperaDe } from "./accionar";
import { conAckDeRama, type EventoFalla } from "./fallas";
import type { Accion } from "./mandos";
import {
  decodificarFotograma, leerMensaje, problemaDeCierre, problemaDeMensaje, textoFin,
  type Fotograma, type InicioVivo, type MandoVivo, type MensajeVivo, type PlcExterno,
} from "./protocolo";
import { empujar, serieDesdeInicio, type SerieViva } from "./serieViva";
import { registrarMuestra, reiniciarHistoria } from "./medicion";

/* La sesión viva del lado del navegador (plan V8.4, F2): abre `WS /api/cosim/vivo` con el token
   del documento (`GET /api/health`) y el escenario elegido, y reparte lo que llega:
   - el `inicio` arma la serie viva y la carga en la store de la marcha (`useMarcha`): el
     reproductor del visor la mueve (cuerpos, cajas, faja), sin tocar `Viewport.tsx`;
   - cada fotograma se suma a esa serie y deja sus señales para el 3D (`sesionViva.valor`) y,
     a 10 Hz, para el panel y la barra (`useVivo`);
   - acks, rechazos, avisos y el fin van a `useVivo`; los cierres se traducen a texto.
   Una sola sesión por pestaña (y por API: el servidor rechaza la segunda con 4423). Si alguien
   quita la marcha (otra marcha, la gravedad, otro proyecto), la sesión se cierra. */

const PUBLICAR_MS = 100;

interface Interno {
  ws: WebSocket | null;
  viva: SerieViva | null;
  inicio: InicioVivo | null;
  nombres: string[];
  valores: Map<string, number>;
  ultimo: Fotograma | null;
  publicadoEn: number;
  /** El `error` que el servidor manda antes de cerrar (su motivo va al detalle). */
  error: string | null;
  escenario: string | null;
  ids: number;
  /** id de acción → señal esperada, para soltarla si se rechaza. */
  esperas: Map<string, string>;
  /** Las fallas con que se abrió la sesión: se mandan al llegar el `inicio` (y al reiniciar). */
  fallasAlAbrir: EventoFalla[];
  /** El PLC externo con que se abrió (plc-en-el-lazo D6): reiniciar lo vuelve a pedir. */
  plcExterno: PlcExterno | null;
}

const s: Interno = {
  ws: null, viva: null, inicio: null, nombres: [], valores: new Map(), ultimo: null, publicadoEn: 0,
  error: null, escenario: null, ids: 0, esperas: new Map(), fallasAlAbrir: [], plcExterno: null,
};

export interface OpcionesSesion {
  /** Cierra la sesión que haya en el servidor (otra pestaña) y abre esta. */
  reemplazar?: boolean;
  /** Fallas ya puestas al empezar (plan cosim-fallas D7): «Probar en vivo» desde otro panel. */
  fallas?: EventoFalla[];
  /** Un PLC de afuera en el lazo (plc-en-el-lazo D6): la sesión no es determinista. */
  plcExterno?: PlcExterno;
}

/** Lo que lee el 3D en cada cuadro (sin pasar por React). */
export const sesionViva = {
  inicio: () => s.inicio,
  tUltimo: (): number | null => s.ultimo?.t ?? null,
  factor: (): number => s.ultimo?.factor ?? 1,
  valor: (nombre: string): number | undefined => s.valores.get(nombre),
};

let suscrito = false;
function vigilarMarcha(): void {
  if (suscrito) return;
  suscrito = true;
  useMarcha.subscribe((m) => {
    if (s.viva && m.serie !== s.viva.serie) soltar(); // otra marcha, la gravedad, otro proyecto
  });
}

/** Corta el socket y olvida la sesión (sin tocar la marcha). */
function soltar(): void {
  const ws = s.ws;
  s.ws = null;
  s.viva = null;
  s.inicio = null;
  s.ultimo = null;
  s.valores.clear();
  s.esperas.clear();
  if (ws && ws.readyState <= WebSocket.OPEN) ws.close(1000);
  useVivo.getState().set({ ...INICIAL });
}

/** La URL del WebSocket (`lugar` = `location`); con un PLC externo, `plc_externo` en JSON (el
 *  servidor la valida: ≤ 1 KB, conector cargado, PLC con programa). */
export function urlSesion(documento: string, escenario: string, reemplazar: boolean,
  plcExterno: PlcExterno | null = null, lugar: { protocol: string; host: string } = location): string {
  const proto = lugar.protocol === "https:" ? "wss" : "ws";
  const q = new URLSearchParams({ documento, escenario });
  if (reemplazar) q.set("reemplazar", "1");
  if (plcExterno && Object.keys(plcExterno).length) q.set("plc_externo", JSON.stringify(plcExterno));
  return `${proto}://${lugar.host}/api/cosim/vivo?${q}`;
}

/** Abre la sesión viva sobre el escenario `escenario` (con `reemplazar`, cierra la que haya;
 *  con `fallas`, las pone en cuanto llega el `inicio`; con `plcExterno`, un PLC de afuera). */
export async function abrirSesion(escenario: string, opciones: OpcionesSesion = {}): Promise<void> {
  const { reemplazar = false, fallas = [], plcExterno = null } = opciones;
  vigilarMarcha();
  const previa = s.ws;
  s.ws = null;
  if (previa && previa.readyState <= WebSocket.OPEN) previa.close(1000);
  s.error = null;
  s.escenario = escenario;
  s.fallasAlAbrir = [...fallas];
  s.plcExterno = plcExterno;
  const st = useVivo.getState();
  st.set({ ...INICIAL, fase: "abriendo", escenario });
  let documento: string;
  try {
    const h = (await fetch("/api/health").then((r) => r.json())) as { documento?: string };
    if (!h.documento) throw new Error("sin documento");
    documento = h.documento;
  } catch {
    st.set({ fase: "error", problema: problemaDeCierre(1006) });
    return;
  }
  const ws = new WebSocket(urlSesion(documento, escenario, reemplazar, plcExterno));
  ws.binaryType = "arraybuffer";
  s.ws = ws;
  ws.onmessage = (ev) => {
    if (s.ws !== ws) return;
    if (typeof ev.data === "string") {
      const m = leerMensaje(ev.data);
      if (m) alMensaje(m);
    } else if (ev.data instanceof ArrayBuffer) {
      const f = decodificarFotograma(ev.data);
      if (f) alFotograma(f);
    }
  };
  ws.onclose = (ev) => {
    if (s.ws !== ws) return; // la cerramos nosotros (reinicio, cerrar)
    s.ws = null;
    const fase = useVivo.getState().fase;
    if (fase === "fin") return;
    useVivo.getState().set({
      fase: "error",
      problema: problemaDeCierre(ev.code, s.error ?? undefined, s.escenario ?? undefined),
    });
  };
}

/** Reabre con el modelo de ahora (y cierra la sesión que haya en el servidor), con las mismas
 *  fallas con que se abrió; las que se pusieron después no vuelven. Sin `reemplazar` (abrir de
 *  nuevo tras un error), no toca la sesión de otra pestaña. */
export function reiniciarSesion(reemplazar = true): Promise<void> {
  return abrirSesion(s.escenario ?? useVivo.getState().escenario ?? "", { reemplazar, fallas: s.fallasAlAbrir,
    plcExterno: s.plcExterno ?? undefined });
}

/** Cierra la sesión y quita la máquina en movimiento del 3D. */
export function cerrarSesion(): void {
  const eraMia = s.viva !== null && useMarcha.getState().serie === s.viva.serie;
  soltar();
  if (eraMia) useMarcha.getState().quitar();
}

/** Manda una acción del operador. `espera`: la señal que debería cambiar y a qué valor. */
export function enviar(accion: Accion, espera?: { senal: string; valor: number }): void {
  const ws = s.ws;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const id = `a${++s.ids}`;
  ws.send(JSON.stringify({ ...accion, id }));
  if (espera) {
    s.esperas.set(id, espera.senal);
    const st = useVivo.getState();
    st.set({ esperadas: { ...st.esperadas, [espera.senal]: espera.valor }, rechazo: null });
  }
}

/** Lo menos que dura apretado un pulsador (ms): un toque más corto (un clic rápido, un toque en
 *  la pantalla) entraría y saldría en la misma ventana de 33 ms y el PLC no lo vería. */
export const PULSO_MIN_MS = 150;
const apretadoEn = new Map<string, number>();

/** Acciona un mando (desde el panel o su pieza 3D) y espera su señal de estado. Un `soltar`
 *  que llega antes de `PULSO_MIN_MS` se demora hasta cumplirlo, como un pulsador real. */
export function accionar(a: Accion, m: MandoVivo): void {
  const clave = `${a.dispositivo}|${a.actuador ?? ""}`;
  if (a.accion === "pulsar") apretadoEn.set(clave, performance.now()); // voseo-interno
  if (a.accion === "soltar") {
    const desde = apretadoEn.get(clave);
    apretadoEn.delete(clave);
    const falta = desde === undefined ? 0 : PULSO_MIN_MS - (performance.now() - desde);
    if (falta > 0) {
      setTimeout(() => enviar(a, esperaDe(a, m)), falta);
      return;
    }
  }
  enviar(a, esperaDe(a, m));
}

/** Un evento del mundo en vivo (el atasco de `EventosVivos.tsx`, la falla de `FallasVivas.tsx`
 *  y su `quitar`); un rechazo llega como el de una acción. */
export function enviarEvento(evento: Record<string, unknown> | EventoFalla): void {
  const ws = s.ws;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ evento, id: `e${++s.ids}` }));
  useVivo.getState().set({ rechazo: null });
}

/** Manda el mensaje de una extensión (una acción o un evento, `problemaDeMensaje`); `false` si no
 *  hay sesión abierta o el mensaje no vale. Su rechazo llega como el de cualquier acción. */
export function enviarMensaje(mensaje: unknown): boolean {
  const ws = s.ws;
  const problema = problemaDeMensaje(mensaje);
  if (problema) {
    console.warn(`Mensaje de extensión a la sesión viva descartado: ${problema}`);
    return false;
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify({ ...(mensaje as object), id: `x${++s.ids}` }));
  useVivo.getState().set({ rechazo: null });
  return true;
}

export function controlar(c: "pausa" | "reanudar" | "parar"): void {
  const ws = s.ws;
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ control: c }));
}

function alMensaje(m: MensajeVivo): void {
  const st = useVivo.getState();
  switch (m.tipo) {
    case "inicio": {
      s.inicio = m;
      s.nombres = [...m.senales];
      s.valores.clear();
      s.ultimo = null;
      s.viva = serieDesdeInicio(m);
      reiniciarHistoria();
      const store = useStore.getState();
      store.clearGravity(); // mueven las mismas mallas
      store.clearPhysics();
      useMarcha.getState().cargar(s.viva.serie);
      st.set({ fase: "corriendo", inicio: m, escenario: m.escenario, problema: null, fin: null, ramasEnFalla: [] });
      for (const f of s.fallasAlAbrir) enviarEvento(f); // entran en el primer intercambio
      return;
    }
    case "senales":
      for (let k = 0; k < m.nombres.length; k++) s.nombres[m.desde + k] = m.nombres[k];
      return;
    case "textos": {
      const textos = { ...st.textos };
      for (const [n, v] of Object.entries(m.valores)) if (typeof v === "string") textos[n] = v;
      st.set({ textos });
      return;
    }
    case "ack": {
      if (m.id) s.esperas.delete(m.id);
      const ramas = conAckDeRama(st.ramasEnFalla, m.evento);
      if (ramas !== st.ramasEnFalla) st.set({ ramasEnFalla: ramas });
      return;
    }
    case "rechazo": {
      const senal = m.id ? s.esperas.get(m.id) : undefined;
      if (m.id) s.esperas.delete(m.id);
      const esperadas = { ...st.esperadas };
      if (senal) delete esperadas[senal];
      st.set({ rechazo: `La máquina no aceptó la acción: ${m.motivo}`, esperadas });
      return;
    }
    case "sesion_vieja":
      st.set({ vieja: m.vieja });
      return;
    case "pausa":
      st.set({ fase: "pausa", pausa: m.motivo ? { motivo: m.motivo, mensaje: m.mensaje } : null });
      return;
    case "reanudar":
      st.set({ fase: "corriendo", pausa: null });
      return;
    case "fin":
      st.set({ fase: "fin", fin: { texto: textoFin(m.motivo), t: m.t ?? st.t } });
      publicar(true);
      return;
    case "error":
      s.error = m.motivo;
      return;
    default:
      return;
  }
}

function alFotograma(f: Fotograma): void {
  if (!s.viva) return;
  empujar(s.viva, f);
  for (let k = 0; k < f.ns; k++) {
    const v = f.senales[k];
    const n = s.nombres[k];
    if (n !== undefined && !Number.isNaN(v)) s.valores.set(n, v);
  }
  s.ultimo = f;
  registrarMuestra(f.t, s.nombres, f.senales); // el osciloscopio y su disparo
  publicar(false);
}

/** Publica t, factor y lecturas a la interfaz, como mucho a 10 Hz. */
function publicar(forzar: boolean): void {
  const ahora = performance.now();
  if (!forzar && ahora - s.publicadoEn < PUBLICAR_MS) return;
  s.publicadoEn = ahora;
  const st = useVivo.getState();
  const lecturas = Object.fromEntries(s.valores);
  let esperadas = st.esperadas;
  const pendientes = new Set(s.esperas.values());
  for (const [senal, v] of Object.entries(st.esperadas)) {
    if (lecturas[senal] === v && !pendientes.has(senal)) {
      if (esperadas === st.esperadas) esperadas = { ...esperadas };
      delete esperadas[senal]; // la señal ya lo muestra
    }
  }
  st.set({ t: s.ultimo?.t ?? st.t, factor: s.ultimo?.factor ?? st.factor, lecturas, esperadas });
}
