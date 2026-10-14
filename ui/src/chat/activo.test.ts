import { afterEach, describe, expect, it, vi } from "vitest";
import { chatActivo, consultarChat, useChatActivo } from "./activo";

const responde = (cuerpo: unknown, status = 200) =>
  vi.fn(async () => new Response(JSON.stringify(cuerpo), { status }));

afterEach(() => {
  vi.unstubAllGlobals();
  useChatActivo.setState({ activo: false });
});

describe("el panel del asistente sigue a la API", () => {
  it("apagado mientras la API no responde", () => {
    expect(chatActivo()).toBe(false);
  });

  it("prendido sólo si la salud dice chat: true", async () => {
    const f = responde({ ok: true, chat: true });
    vi.stubGlobal("fetch", f);
    expect(await consultarChat()).toBe(true);
    expect(chatActivo()).toBe(true);
    expect(useChatActivo.getState().activo).toBe(true);
    expect(f).toHaveBeenCalledWith("/api/health");
  });

  it("apagado si dice false, si no lo dice o si falla", async () => {
    for (const f of [
      responde({ chat: false }),
      responde({ ok: true }),
      responde({ chat: "1" }),
      responde({ detail: "caído" }, 500),
      vi.fn(async () => {
        throw new TypeError("sin red");
      }),
    ]) {
      vi.stubGlobal("fetch", responde({ chat: true }));
      await consultarChat();
      vi.stubGlobal("fetch", f);
      expect(await consultarChat()).toBe(false);
      expect(chatActivo()).toBe(false);
    }
  });
});
