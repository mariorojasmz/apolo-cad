import { afterEach, describe, expect, it, vi } from "vitest";
import { guardarModo, leerModo, PANTALLA_KEY } from "./estado";

/* La store del visor: modo por defecto «visor», recordado en localStorage y tolerante a un
   almacén que lanza (sitio bloqueado, modo privado). Vitest corre en node: el localStorage
   es un doble. */

function almacenFalso(inicial: Record<string, string> = {}) {
  const datos = new Map(Object.entries(inicial));
  return {
    datos,
    getItem: (k: string) => datos.get(k) ?? null,
    setItem: (k: string, v: string) => void datos.set(k, v),
  };
}

const almacenQueLanza = {
  getItem: () => {
    throw new Error("SecurityError");
  },
  setItem: () => {
    throw new Error("QuotaExceededError");
  },
};

/** Importa la store de cero con `localStorage` = `ls` (el modo se lee al crearla). */
async function storeCon(ls: unknown) {
  vi.resetModules();
  vi.stubGlobal("localStorage", ls);
  return (await import("./estado")).useVisor;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("leerModo / guardarModo", () => {
  it("sin nada guardado, el modo es visor", () => {
    expect(leerModo(almacenFalso())).toBe("visor");
    expect(leerModo(null)).toBe("visor");
  });

  it("lee completo y descarta lo que no reconoce", () => {
    expect(leerModo(almacenFalso({ [PANTALLA_KEY]: "completo" }))).toBe("completo");
    expect(leerModo(almacenFalso({ [PANTALLA_KEY]: "visor" }))).toBe("visor");
    expect(leerModo(almacenFalso({ [PANTALLA_KEY]: "otra-cosa" }))).toBe("visor");
  });

  it("tolera un almacén que lanza", () => {
    expect(leerModo(almacenQueLanza)).toBe("visor");
    expect(() => guardarModo("completo", almacenQueLanza)).not.toThrow();
  });

  it("guarda el modo en su clave", () => {
    const a = almacenFalso();
    guardarModo("completo", a);
    expect(a.datos.get(PANTALLA_KEY)).toBe("completo");
  });
});

describe("useVisor", () => {
  it("arranca en visor sin nada guardado", async () => {
    const useVisor = await storeCon(almacenFalso());
    expect(useVisor.getState().modo).toBe("visor");
  });

  it("arranca en el modo recordado", async () => {
    const useVisor = await storeCon(almacenFalso({ [PANTALLA_KEY]: "completo" }));
    expect(useVisor.getState().modo).toBe("completo");
  });

  it("arranca en visor si localStorage lanza o no existe", async () => {
    expect((await storeCon(almacenQueLanza)).getState().modo).toBe("visor");
    expect((await storeCon(undefined)).getState().modo).toBe("visor");
  });

  it("setModo persiste y cierra los cajones", async () => {
    const a = almacenFalso();
    const useVisor = await storeCon(a);
    const s = useVisor.getState();
    s.toggleIzq();
    s.abrirDer("bom");
    expect(useVisor.getState()).toMatchObject({ cajonIzq: true, cajonDer: "bom" });
    useVisor.getState().setModo("completo");
    expect(a.datos.get(PANTALLA_KEY)).toBe("completo");
    expect(useVisor.getState()).toMatchObject({ modo: "completo", cajonIzq: false, cajonDer: null });
  });

  it("setModo no revienta si el almacén lanza", async () => {
    const useVisor = await storeCon(almacenQueLanza);
    expect(() => useVisor.getState().setModo("completo")).not.toThrow();
    expect(useVisor.getState().modo).toBe("completo");
  });

  it("el cajón derecho aloja un panel a la vez y se cierra al repetirlo", async () => {
    const useVisor = await storeCon(almacenFalso());
    const s = useVisor.getState();
    s.abrirDer("bom");
    s.abrirDer("checks");
    expect(useVisor.getState().cajonDer).toBe("checks");
    useVisor.getState().abrirDer("checks");
    expect(useVisor.getState().cajonDer).toBeNull();
  });

  it("marcar publica el aviso y las marcas; descartar deja las marcas", async () => {
    const useVisor = await storeCon(almacenFalso());
    useVisor.getState().marcar({ nuevos: ["c9"], cambiados: ["c2"], eliminados: 1 }, 1000);
    expect(useVisor.getState()).toMatchObject({
      aviso: { nuevos: ["c9"], cambiados: ["c2"], eliminados: 1, en: 1000 },
      marcados: ["c9", "c2"],
      nuevas: ["c9"],
      pulso: 1000,
    });
    useVisor.getState().repulsar(2000);
    expect(useVisor.getState().pulso).toBe(2000);
    useVisor.getState().descartarAviso();
    expect(useVisor.getState()).toMatchObject({ aviso: null, marcados: ["c9", "c2"], nuevas: ["c9"] });
  });

  it("marcar sin cambios no toca nada", async () => {
    const useVisor = await storeCon(almacenFalso());
    useVisor.getState().marcar({ nuevos: [], cambiados: [], eliminados: 0 }, 1000);
    expect(useVisor.getState()).toMatchObject({ aviso: null, marcados: [], pulso: 0 });
  });
});
