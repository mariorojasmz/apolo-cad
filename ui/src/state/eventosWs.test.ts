import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { connectWs } from "../api";
import {
  avisoJob, EVENTO_JOB, EVENTO_WS_RECONECTADO, mensajeWs, publicarJob, publicarReconexion, type AvisoJob,
} from "./eventosWs";

/* Los avisos de jobs del WS (plan modo-visor, D10): qué mensaje cuenta como aviso válido, y el
   cableado en `connectWs` con un WebSocket simulado (vitest corre en node: `window` es un
   EventTarget de prueba). */

describe("mensajeWs", () => {
  it("un objeto JSON pasa; lo que no es JSON, no es objeto o no es texto, da null", () => {
    expect(mensajeWs('{"type":"document_changed"}')).toEqual({ type: "document_changed" });
    expect(mensajeWs("no es json")).toBeNull();
    expect(mensajeWs("null")).toBeNull();
    expect(mensajeWs("[1,2]")).toBeNull();
    expect(mensajeWs('"job"')).toBeNull();
    expect(mensajeWs(new ArrayBuffer(4))).toBeNull();
  });
});

describe("avisoJob", () => {
  it("los tres estados del servidor son válidos", () => {
    for (const estado of ["corriendo", "ok", "error"] as const)
      expect(avisoJob({ type: "job", job_id: "a1b2c3d4", estado })).toEqual({ job_id: "a1b2c3d4", estado });
  });

  it("otro tipo, sin id, con id vacío o no texto, o con un estado desconocido, se ignora", () => {
    expect(avisoJob(null)).toBeNull();
    expect(avisoJob({ type: "document_changed" })).toBeNull();
    expect(avisoJob({ type: "job", estado: "ok" })).toBeNull();
    expect(avisoJob({ type: "job", job_id: "", estado: "ok" })).toBeNull();
    expect(avisoJob({ type: "job", job_id: 7, estado: "ok" })).toBeNull();
    expect(avisoJob({ type: "job", job_id: "a1", estado: "encolado" })).toBeNull();
    expect(avisoJob({ type: "job", job_id: "a1" })).toBeNull();
  });

  it("descarta los campos que no son del aviso", () => {
    expect(avisoJob({ type: "job", job_id: "a1", estado: "ok", resultado: { x: 1 } })).toEqual({ job_id: "a1", estado: "ok" });
  });
});

describe("publicarJob y publicarReconexion", () => {
  it("despachan su evento sólo con un aviso válido; sin destino no hacen nada", () => {
    const destino = new EventTarget();
    const recibidos: AvisoJob[] = [];
    let reconexiones = 0;
    destino.addEventListener(EVENTO_JOB, (ev) => recibidos.push((ev as CustomEvent<AvisoJob>).detail));
    destino.addEventListener(EVENTO_WS_RECONECTADO, () => reconexiones++);

    publicarJob({ type: "job", job_id: "a1", estado: "corriendo" }, destino);
    publicarJob({ type: "job", job_id: "a1", estado: "raro" }, destino);
    publicarJob(null, destino);
    publicarReconexion(destino);
    expect(recibidos).toEqual([{ job_id: "a1", estado: "corriendo" }]);
    expect(reconexiones).toBe(1);

    expect(() => publicarJob({ type: "job", job_id: "a1", estado: "ok" }, undefined)).not.toThrow();
    expect(() => publicarReconexion(undefined)).not.toThrow();
  });
});

/** WebSocket de prueba: guarda cada instancia para dispararle sus manejadores. */
class WsFalso {
  static abiertos: WsFalso[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) {
    WsFalso.abiertos.push(this);
  }
  close() {}
}

describe("connectWs", () => {
  let ventana: EventTarget;
  let eventos: string[];
  let cerrar: () => void;

  beforeEach(() => {
    vi.useFakeTimers();
    WsFalso.abiertos = [];
    ventana = new EventTarget();
    eventos = [];
    ventana.addEventListener(EVENTO_JOB, (ev) => {
      const d = (ev as CustomEvent<AvisoJob>).detail;
      eventos.push(`job ${d.job_id} ${d.estado}`);
    });
    ventana.addEventListener(EVENTO_WS_RECONECTADO, () => eventos.push("reconectado"));
    vi.stubGlobal("window", ventana);
    vi.stubGlobal("location", { protocol: "http:", host: "127.0.0.1:8000" });
    vi.stubGlobal("WebSocket", WsFalso);
  });
  afterEach(() => {
    cerrar?.();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("despacha los avisos de job y sigue llamando a onChanged con document_changed", () => {
    const onChanged = vi.fn();
    cerrar = connectWs(onChanged);
    const ws = WsFalso.abiertos[0];
    ws.onopen?.();
    ws.onmessage?.({ data: JSON.stringify({ type: "job", job_id: "a1", estado: "corriendo" }) });
    ws.onmessage?.({ data: JSON.stringify({ type: "document_changed" }) });
    ws.onmessage?.({ data: JSON.stringify({ type: "job", job_id: "a1", estado: "ok" }) });
    ws.onmessage?.({ data: "roto{" });
    ws.onmessage?.({ data: JSON.stringify({ type: "autosave_failed" }) });
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(eventos).toEqual(["job a1 corriendo", "job a1 ok"]);
  });

  it("la primera conexión no avisa reconexión; la siguiente sí, junto con onReconnect", () => {
    const onReconnect = vi.fn();
    cerrar = connectWs(() => {}, onReconnect);
    WsFalso.abiertos[0].onopen?.();
    expect(eventos).toEqual([]);
    expect(onReconnect).not.toHaveBeenCalled();

    WsFalso.abiertos[0].onclose?.();
    vi.advanceTimersByTime(2000); // reintenta a los 2 s
    expect(WsFalso.abiertos).toHaveLength(2);
    WsFalso.abiertos[1].onopen?.();
    expect(eventos).toEqual(["reconectado"]);
    expect(onReconnect).toHaveBeenCalledTimes(1);
  });
});
