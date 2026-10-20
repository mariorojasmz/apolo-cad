import { afterEach, describe, expect, it, vi } from "vitest";
import {
  abrirConGuion, grabarEnSesion, grabarVideo, reportarFallo, type AperturaGrabacion, type OpcionesVideo,
} from "./grabador";

/* Cliente de la grabación (video-realista D4) contra un `fetch` simulado: el orden de las
   peticiones, cada cuadro subido una vez con su tipo, el cierre con música y qué pasa cuando algo
   falla (antes del cierre se descarta la sesión; si falla el cierre, los cuadros quedan). */

interface Peticion {
  metodo: string;
  url: string;
  tipo?: string;
  cuerpo?: unknown;
}

function api(fallar: (p: Peticion) => { status: number; detail: string } | null = () => null) {
  const peticiones: Peticion[] = [];
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const headers = (init?.headers ?? {}) as Record<string, string>;
    const p: Peticion = { metodo: init?.method ?? "GET", url, tipo: headers["Content-Type"] };
    if (typeof init?.body === "string") p.cuerpo = JSON.parse(init.body);
    else if (init?.body instanceof Blob) p.cuerpo = await init.body.text();
    peticiones.push(p);
    const error = fallar(p);
    if (error) return new Response(JSON.stringify({ detail: error.detail }), { status: error.status });
    let datos: unknown = {};
    if (p.metodo === "POST" && url === "/api/video/grabacion") {
      datos = { sesion: "abc123", ...(p.cuerpo as object), estimado_bytes: 1, espacio_libre_bytes: 9 };
    } else if (url === "/api/video/guion") {
      datos = { guion: { titulo: "Faja" }, plan: { cuadros: 3 } };
    } else if (url.endsWith("/cerrar")) {
      datos = { estado: "lista", informe: { video: "C:/x/video.mp4", cuadros: 5, duracion_s: 0.2 } };
    }
    return new Response(JSON.stringify(datos), { status: 200 });
  });
  vi.stubGlobal("fetch", fetch);
  return peticiones;
}

const opciones = (extra: Partial<OpcionesVideo> = {}): OpcionesVideo => ({
  ancho: 1920, alto: 1080, fps: 25, formato: "jpeg", cuadros: 5,
  dibujar: async (n) => ({ foto: Promise.resolve(new Blob([`cuadro ${n}`], { type: "image/jpeg" })) }),
  ...extra,
});

afterEach(() => vi.unstubAllGlobals());

describe("grabarVideo", () => {
  it("abre, sube cada cuadro una vez con su tipo y cierra", async () => {
    const peticiones = api();
    const r = await grabarVideo(opciones({ musica: "C:/musica/pista.mp3" }));
    expect(peticiones[0]).toMatchObject({
      metodo: "POST", url: "/api/video/grabacion",
      cuerpo: { ancho: 1920, alto: 1080, fps: 25, formato: "jpeg", cuadros: 5 },
    });
    const cuadros = peticiones.filter((p) => p.url.includes("/cuadro/"));
    expect(cuadros.map((p) => p.url).sort()).toEqual(
      [0, 1, 2, 3, 4].map((n) => `/api/video/grabacion/abc123/cuadro/${n}`));
    for (const p of cuadros) {
      expect(p.tipo).toBe("image/jpeg");
      expect(p.cuerpo).toBe(`cuadro ${p.url.split("/").pop()}`);
    }
    const ultima = peticiones[peticiones.length - 1];
    expect(ultima).toMatchObject({
      metodo: "POST", url: "/api/video/grabacion/abc123/cerrar",
      cuerpo: { musica: "C:/musica/pista.mp3" },
    });
    expect(peticiones).toHaveLength(7); // abrir + 5 cuadros + cerrar, nada más
    expect(r.informe.video).toBe("C:/x/video.mp4");
    expect(r.apertura.sesion).toBe("abc123");
  });

  it("si la API rechaza un cuadro, descarta la sesión y no cierra", async () => {
    const peticiones = api((p) => (p.url.endsWith("/cuadro/2")
      ? { status: 400, detail: "El cuadro 2 mide 1280×720 y la grabación es de 1920×1080." } : null));
    await expect(grabarVideo(opciones())).rejects.toThrow("El cuadro 2 mide 1280×720");
    expect(peticiones.some((p) => p.url.endsWith("/cerrar"))).toBe(false);
    expect(peticiones[peticiones.length - 1]).toMatchObject({
      metodo: "DELETE", url: "/api/video/grabacion/abc123",
    });
  });

  it("si no hay disco, no abre nada ni dibuja", async () => {
    const peticiones = api((p) => (p.url === "/api/video/grabacion"
      ? { status: 507, detail: "La grabación necesita ~3,2 GB para sus cuadros." } : null));
    const dibujar = vi.fn();
    await expect(grabarVideo(opciones({ dibujar }))).rejects.toThrow("necesita ~3,2 GB");
    expect(dibujar).not.toHaveBeenCalled();
    expect(peticiones).toHaveLength(1);
  });

  it("si falla la codificación, los cuadros quedan en la sesión", async () => {
    const peticiones = api((p) => (p.url.endsWith("/cerrar")
      ? { status: 503, detail: "No encuentro ffmpeg." } : null));
    await expect(grabarVideo(opciones())).rejects.toThrow("No encuentro ffmpeg.");
    expect(peticiones.some((p) => p.metodo === "DELETE")).toBe(false);
  });

  it("avisa al abrir y del avance", async () => {
    api();
    const alAbrir = vi.fn();
    const avance: number[] = [];
    await grabarVideo(opciones({ alAbrir, progreso: (a) => avance.push(a.subidos) }));
    expect(alAbrir).toHaveBeenCalledWith(expect.objectContaining({ sesion: "abc123" }));
    expect(Math.max(...avance)).toBe(5);
  });
});

describe("grabarEnSesion y las rutas del guion (F3)", () => {
  const apertura = { sesion: "abc123" } as AperturaGrabacion;
  const op = { fps: 25, cuadros: 3, dibujar: opciones().dibujar };

  it("sube a la sesión abierta y cierra sin pisar lo que fijó quien la abrió", async () => {
    const peticiones = api();
    await grabarEnSesion(apertura, op);
    expect(peticiones.filter((p) => p.url.includes("/cuadro/"))).toHaveLength(3);
    expect(peticiones.some((p) => p.url === "/api/video/grabacion")).toBe(false); // no abre otra
    expect(peticiones[peticiones.length - 1]).toMatchObject({ url: "/api/video/grabacion/abc123/cerrar", cuerpo: {} });
  });

  it("la sesión del CLI no se descarta al fallar: el CLI lee el motivo", async () => {
    const peticiones = api((p) => (p.url.endsWith("/cuadro/1") ? { status: 409, detail: "ya llegó" } : null));
    await expect(grabarEnSesion(apertura, op, { descartar: false })).rejects.toThrow("ya llegó");
    expect(peticiones.some((p) => p.metodo === "DELETE")).toBe(false);
  });

  it("el fallo lleva el motivo, y el botón abre la sesión con el guion del proyecto", async () => {
    const peticiones = api();
    await reportarFallo("abc123", "Sin GPU", "sin_gpu");
    expect(peticiones[0]).toMatchObject({
      metodo: "POST", url: "/api/video/grabacion/abc123/fallo", cuerpo: { mensaje: "Sin GPU", motivo: "sin_gpu" },
    });
    await abrirConGuion();
    expect(peticiones[1]).toMatchObject({ metodo: "POST", url: "/api/video/guion" });
    expect(peticiones[2]).toMatchObject({
      metodo: "POST", url: "/api/video/grabacion", cuerpo: { guion: { titulo: "Faja" }, plan: { cuadros: 3 } },
    });
  });
});
