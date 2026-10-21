import { afterEach, describe, expect, it, vi } from "vitest";
import { grabador, grabarSiLoPiden, registrarGrabador, sesionDeUrl } from "./registro";
import { SinGpu } from "./guionVista";

/* El modo sin ventana de `publicar generar --render navegador` (video-realista D7): la página
   lee `?grabar=<sesion>`, graba con el grabador que registró el visor y, si no puede, deja la
   sesión «fallida» con su motivo (sin GPU → el CLI cae a VTK). */

afterEach(() => vi.unstubAllGlobals());

function fetchSimulado() {
  const llamadas: { url: string; cuerpo: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    llamadas.push({ url, cuerpo: typeof init?.body === "string" ? JSON.parse(init.body) : null });
    return new Response("{}", { status: 200 });
  }));
  return llamadas;
}

const esperarA = async (cond: () => boolean) => {
  for (let i = 0; i < 100 && !cond(); i++) await new Promise((r) => setTimeout(r, 5));
};

describe("grabar desde la URL", () => {
  it("lee sólo una sesión con forma de id", () => {
    expect(sesionDeUrl("?grabar=3f9a0c12bb01")).toBe("3f9a0c12bb01");
    expect(sesionDeUrl("?x=1")).toBeNull();
    expect(sesionDeUrl("?grabar=../../etc")).toBeNull();
  });

  it("graba la sesión con el grabador del visor, sin descartarla", async () => {
    fetchSimulado();
    const grabar = vi.fn(async () => ({}) as never);
    const soltar = registrarGrabador(grabar);
    grabarSiLoPiden("?grabar=abcdef123456");
    await esperarA(() => grabar.mock.calls.length > 0);
    expect(grabar).toHaveBeenCalledWith("abcdef123456", { descartar: false });
    soltar();
    expect(grabador()).toBeNull();
  });

  it("`--nivel maximo` del CLI llega al grabador como el trazado de rayos", async () => {
    fetchSimulado();
    const grabar = vi.fn(async () => ({}) as never);
    const soltar = registrarGrabador(grabar);
    grabarSiLoPiden("?grabar=abcdef123456&nivel=maximo&muestras=64");
    await esperarA(() => grabar.mock.calls.length > 0);
    expect(grabar).toHaveBeenCalledWith("abcdef123456",
      { descartar: false, nivel: "maximo", trazado: { muestras: 64, semilla: undefined } });
    soltar();
  });

  it("sin GPU deja la sesión fallida con motivo «sin_gpu»; otro error, con «error»", async () => {
    const llamadas = fetchSimulado();
    const soltar = registrarGrabador(async () => { throw new SinGpu("Sin GPU"); });
    grabarSiLoPiden("?grabar=abcdef123456");
    await esperarA(() => llamadas.length > 0);
    expect(llamadas[0]).toEqual({
      url: "/api/video/grabacion/abcdef123456/fallo", cuerpo: { mensaje: "Sin GPU", motivo: "sin_gpu" },
    });
    soltar();
    registrarGrabador(async () => { throw new Error("se cayó"); });
    grabarSiLoPiden("?grabar=abcdef123456");
    await esperarA(() => llamadas.length > 1);
    expect(llamadas[1].cuerpo).toEqual({ mensaje: "se cayó", motivo: "error" });
  });
});
