import { describe, expect, it } from "vitest";
import { cajonQueCierraEsc, esCampoDeTexto, panelesDelMenu } from "./cajones";
import { useVisor } from "./estado";

const libre = { prioridad: false, enCampo: false };

describe("Esc y los cajones del visor", () => {
  it("cierra primero el derecho, después el izquierdo", () => {
    expect(cajonQueCierraEsc({ cajonIzq: true, cajonDer: "bom" }, libre)).toBe("der");
    expect(cajonQueCierraEsc({ cajonIzq: true, cajonDer: null }, libre)).toBe("izq");
    expect(cajonQueCierraEsc({ cajonIzq: false, cajonDer: "chat" }, libre)).toBe("der");
  });

  it("sin cajones abiertos no cierra nada (Esc sigue a los atajos del viewport)", () => {
    expect(cajonQueCierraEsc({ cajonIzq: false, cajonDer: null }, libre)).toBeNull();
  });

  it("un diálogo o menú abierto va antes: no cierra el cajón", () => {
    expect(cajonQueCierraEsc({ cajonIzq: true, cajonDer: "bom" }, { prioridad: true, enCampo: false })).toBeNull();
  });

  it("dentro de un campo de texto, Esc es del campo", () => {
    expect(cajonQueCierraEsc({ cajonIzq: true, cajonDer: "chat" }, { prioridad: false, enCampo: true })).toBeNull();
  });

  it("cerrarCajon cierra sólo el lado pedido", () => {
    const v = useVisor.getState();
    v.cerrarCajones();
    v.toggleIzq();
    v.abrirDer("bom");
    useVisor.getState().cerrarCajon("der");
    expect(useVisor.getState()).toMatchObject({ cajonIzq: true, cajonDer: null });
    useVisor.getState().abrirDer("history");
    useVisor.getState().cerrarCajon("izq");
    expect(useVisor.getState()).toMatchObject({ cajonIzq: false, cajonDer: "history" });
    useVisor.getState().cerrarCajones();
  });
});

describe("esCampoDeTexto", () => {
  it("reconoce input, textarea, select y contenido editable", () => {
    expect(esCampoDeTexto({ tagName: "INPUT" })).toBe(true);
    expect(esCampoDeTexto({ tagName: "TEXTAREA" })).toBe(true);
    expect(esCampoDeTexto({ tagName: "SELECT" })).toBe(true);
    expect(esCampoDeTexto({ tagName: "DIV", isContentEditable: true })).toBe(true);
  });

  it("un botón, el cuerpo de la página o nada no son campos", () => {
    expect(esCampoDeTexto({ tagName: "BUTTON" })).toBe(false);
    expect(esCampoDeTexto({ tagName: "BODY", isContentEditable: false })).toBe(false);
    expect(esCampoDeTexto(null)).toBe(false);
  });
});

describe("menú «Más» de la barra de paneles", () => {
  it("lleva las herramientas sin botón propio, en su orden", () => {
    const herramientas = ["history", "reqs", "bom", "checks", "kin", "mates", "fisica", "ensamblaje", "boceto"];
    expect(panelesDelMenu(herramientas, ["bom", "checks", "history"])).toEqual([
      "reqs", "kin", "mates", "fisica", "ensamblaje", "boceto",
    ]);
  });

  it("una herramienta nueva aparece sola en el menú", () => {
    expect(panelesDelMenu(["bom", "nueva"], ["bom"])).toEqual(["nueva"]);
  });
});
