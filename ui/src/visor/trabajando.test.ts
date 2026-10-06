import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EVENTO_JOB, EVENTO_WS_RECONECTADO, type EstadoJob } from "../state/eventosWs";
import { useVisor } from "./estado";
import { aplicarJob, escucharJobs, JOB_COLGADO_MS, podarColgados, proximoVencimiento } from "./trabajando";

/* «El agente está trabajando…» (plan modo-visor, D10): el conjunto de jobs corriendo, puro, y
   su instalación sobre los eventos que publica `connectWs`, con la red de seguridad de los
   10 minutos. */

const MIN = 60 * 1000;

describe("aplicarJob", () => {
  it("corriendo agrega, ok y error quitan, sin tocar el mapa de entrada", () => {
    const vacio = new Map<string, number>();
    const uno = aplicarJob(vacio, { job_id: "a", estado: "corriendo" }, 100);
    expect([...uno]).toEqual([["a", 100]]);
    expect(vacio.size).toBe(0);
    const dos = aplicarJob(uno, { job_id: "b", estado: "corriendo" }, 200);
    expect([...aplicarJob(dos, { job_id: "a", estado: "ok" }, 300).keys()]).toEqual(["b"]);
    expect([...aplicarJob(dos, { job_id: "b", estado: "error" }, 300).keys()]).toEqual(["a"]);
  });

  it("un corriendo repetido conserva su inicio; un fin sin inicio no hace nada", () => {
    const uno = aplicarJob(new Map(), { job_id: "a", estado: "corriendo" }, 100);
    expect(aplicarJob(uno, { job_id: "a", estado: "corriendo" }, 999).get("a")).toBe(100);
    expect([...aplicarJob(uno, { job_id: "zz", estado: "ok" }, 200)]).toEqual([["a", 100]]);
  });
});

describe("podarColgados y proximoVencimiento", () => {
  it("quita los que llevan 10 minutos o más; el vencimiento es el del más viejo", () => {
    const jobs = new Map([["viejo", 0], ["nuevo", 5 * MIN]]);
    expect(proximoVencimiento(jobs)).toBe(JOB_COLGADO_MS);
    expect([...podarColgados(jobs, JOB_COLGADO_MS - 1).keys()]).toEqual(["viejo", "nuevo"]);
    expect([...podarColgados(jobs, JOB_COLGADO_MS).keys()]).toEqual(["nuevo"]);
    expect(proximoVencimiento(new Map())).toBeNull();
  });
});

describe("escucharJobs", () => {
  let origen: EventTarget;
  let dejar: () => void;
  const job = (job_id: string, estado: EstadoJob) =>
    origen.dispatchEvent(new CustomEvent(EVENTO_JOB, { detail: { job_id, estado } }));
  const trabajando = () => useVisor.getState().trabajando;

  beforeEach(() => {
    vi.useFakeTimers();
    useVisor.setState({ trabajando: false, aviso: null, marcados: [], nuevas: [] });
    origen = new EventTarget();
    dejar = escucharJobs(origen);
  });
  afterEach(() => {
    dejar();
    vi.useRealTimers();
  });

  it("trabaja mientras quede algún job corriendo", () => {
    job("a", "corriendo");
    expect(trabajando()).toBe(true);
    job("b", "corriendo");
    job("a", "ok");
    expect(trabajando()).toBe(true);
    job("b", "error");
    expect(trabajando()).toBe(false);
  });

  it("un aviso roto o con un estado desconocido no cambia nada", () => {
    origen.dispatchEvent(new CustomEvent(EVENTO_JOB, { detail: null }));
    origen.dispatchEvent(new CustomEvent(EVENTO_JOB, { detail: { job_id: "a", estado: "encolado" } }));
    origen.dispatchEvent(new CustomEvent(EVENTO_JOB, { detail: { estado: "corriendo" } }));
    expect(trabajando()).toBe(false);
  });

  it("la reconexión del WS vacía el conjunto", () => {
    job("a", "corriendo");
    origen.dispatchEvent(new Event(EVENTO_WS_RECONECTADO));
    expect(trabajando()).toBe(false);
    job("a", "ok"); // el fin que llega después no rompe nada
    expect(trabajando()).toBe(false);
  });

  it("un job colgado más de 10 minutos se descarta solo, sin que llegue otro aviso", () => {
    job("a", "corriendo");
    vi.advanceTimersByTime(5 * MIN);
    job("b", "corriendo");
    vi.advanceTimersByTime(JOB_COLGADO_MS - 5 * MIN - 1);
    expect(trabajando()).toBe(true);
    vi.advanceTimersByTime(1); // vence «a»; «b» sigue
    expect(trabajando()).toBe(true);
    vi.advanceTimersByTime(5 * MIN); // vence «b»
    expect(trabajando()).toBe(false);
  });

  it("al empezar a trabajar descarta el aviso de cambios viejo; las marcas quedan", () => {
    useVisor.getState().marcar({ nuevos: ["n1"], cambiados: ["c1"], eliminados: 0 });
    job("a", "corriendo");
    expect(useVisor.getState()).toMatchObject({ trabajando: true, aviso: null, marcados: ["n1", "c1"], nuevas: ["n1"] });
  });

  it("un aviso de cambios que llega mientras trabaja se conserva", () => {
    job("a", "corriendo");
    useVisor.getState().marcar({ nuevos: [], cambiados: ["c1"], eliminados: 0 });
    job("b", "corriendo"); // ya trabajaba: no es un comienzo
    job("a", "ok");
    job("b", "ok");
    expect(useVisor.getState().aviso).toMatchObject({ cambiados: ["c1"] });
  });

  it("al dejar de escuchar, ni los avisos ni el temporizador cambian nada", () => {
    job("a", "corriendo");
    dejar();
    job("a", "ok");
    vi.advanceTimersByTime(JOB_COLGADO_MS);
    expect(trabajando()).toBe(true);
  });
});
