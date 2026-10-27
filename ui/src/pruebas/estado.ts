import { create } from "zustand";
import { detalleDeError } from "../api";
import { encolar, esperarJob } from "../state/jobs";
import { abrirPanel } from "../vivo/abrirPanel";
import { abrirSesion } from "../vivo/sesion";
import type { Corrida } from "./vista";
import type { DetallePrueba, PanelPruebasOut } from "./tipos";

/* El estado del panel «Pruebas» (plan visor-para-evaluar D1–D5), fuera del store global: el
   panel lo lee con selectores primitivos. `cargarPruebas` lee la API; `correrPrueba` encola la
   co-simulación como job (origen «visor», en la cola de la co-simulación: respeta sus locks) y
   la sigue hasta el final; `verEnVivo` abre la sesión viva con ese escenario, como «Mandos». */

export interface EstadoPruebas {
  panel: PanelPruebasOut | null;
  leido: boolean;
  error: string | null;
  /** El escenario abierto y su detalle (null mientras llega). */
  abierto: string | null;
  detalle: DetallePrueba | null;
  /** Las corridas en curso, por escenario. */
  corridas: Record<string, Corrida>;
  /** Lo que salió mal al correr uno (el texto del servidor), por escenario. */
  fallos: Record<string, string>;
  set: (p: Partial<EstadoPruebas>) => void;
}

export const usePruebas = create<EstadoPruebas>((set) => ({
  panel: null,
  leido: false,
  error: null,
  abierto: null,
  detalle: null,
  corridas: {},
  fallos: {},
  set: (p) => set(p),
}));

let pedido = 0;

async function leer<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await detalleDeError(r)) ?? r.statusText);
  return (await r.json()) as T;
}

/** Lee la lista y, si hay uno abierto, su detalle. Una respuesta vieja se descarta. */
export async function cargarPruebas(): Promise<void> {
  const n = ++pedido;
  try {
    const panel = await leer<PanelPruebasOut>("/api/pruebas");
    if (n !== pedido) return;
    const { abierto } = usePruebas.getState();
    const sigue = abierto && panel.escenarios.some((e) => e.nombre === abierto) ? abierto : null;
    usePruebas.getState().set({ panel, leido: true, error: null, abierto: sigue, ...(sigue ? {} : { detalle: null }) });
    if (sigue) await cargarDetalle(sigue);
  } catch (e) {
    if (n !== pedido) return;
    usePruebas.getState().set({ leido: true, error: e instanceof Error ? e.message : String(e) });
  }
}

async function cargarDetalle(nombre: string): Promise<void> {
  try {
    const d = await leer<DetallePrueba>(`/api/pruebas/${encodeURIComponent(nombre)}`);
    if (usePruebas.getState().abierto === nombre) usePruebas.getState().set({ detalle: d });
  } catch {
    // se borró mientras tanto: la próxima lectura de la lista lo cierra
  }
}

/** Abre (o cierra, si ya estaba abierto) un escenario del panel. */
export function alternarPrueba(nombre: string): void {
  const st = usePruebas.getState();
  if (st.abierto === nombre) {
    st.set({ abierto: null, detalle: null });
    return;
  }
  st.set({ abierto: nombre, detalle: null });
  void cargarDetalle(nombre);
}

function ponerCorrida(nombre: string, c: Corrida | null): void {
  const corridas = { ...usePruebas.getState().corridas };
  if (c) corridas[nombre] = c;
  else delete corridas[nombre];
  usePruebas.getState().set({ corridas });
}

/** Corre el escenario como job y lo sigue hasta que termina; después vuelve a leer el panel. */
export async function correrPrueba(nombre: string, estimadoS?: number): Promise<void> {
  const st = usePruebas.getState();
  if (st.corridas[nombre]) return;
  const fallos = { ...st.fallos };
  delete fallos[nombre];
  st.set({ fallos });
  try {
    const jobId = await encolar("/api/cosim/run?async=true&origen=visor", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ escenario: nombre }),
    });
    ponerCorrida(nombre, { jobId, estado: "encolado", desde: null, estimadoS });
    await esperarJob(jobId, (e) => {
      const c = usePruebas.getState().corridas[nombre];
      if (c && e.estado === "corriendo" && c.estado !== "corriendo") ponerCorrida(nombre, { ...c, estado: "corriendo", desde: Date.now() });
    });
  } catch (e) {
    usePruebas.getState().set({ fallos: { ...usePruebas.getState().fallos, [nombre]: e instanceof Error ? e.message : String(e) } });
  } finally {
    ponerCorrida(nombre, null);
    await cargarPruebas();
  }
}

/** La sesión viva con ese escenario de base, en el panel «Mandos» (lo mismo que su selector). */
export async function verEnVivo(nombre: string): Promise<void> {
  await abrirPanel("mandos");
  await abrirSesion(nombre);
}
