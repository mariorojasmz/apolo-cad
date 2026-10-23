import { describe, expect, it } from "vitest";
import { CABECERA, decodificarFotograma, leerMensaje, problemaDeCierre, textoFin } from "./protocolo";

/* El protocolo de la sesión viva (plan V8.4, Bitácora de F1): el fotograma binario float32 con
   su cabecera, los JSON cortos y el texto de cada cierre. */

/** Un fotograma como lo empaca `cosim/vivo_fotograma.py::Fotograma.empacar`. */
function fotogramaBinario(o: {
  t: number; factor?: number; cuerpos?: number[][]; productos?: number[][]; juntas?: number[];
  bandas?: number[]; senales?: number[];
}): ArrayBuffer {
  const cuerpos = o.cuerpos ?? [];
  const productos = o.productos ?? [];
  const juntas = o.juntas ?? [];
  const bandas = o.bandas ?? [];
  const senales = o.senales ?? [];
  const datos = [1, o.t, o.factor ?? 1, cuerpos.length, productos.length, juntas.length, bandas.length, senales.length,
    ...cuerpos.flat(), ...productos.flat(), ...juntas, ...bandas, ...senales];
  const buf = new ArrayBuffer(datos.length * 4);
  const v = new DataView(buf);
  datos.forEach((x, i) => v.setFloat32(i * 4, x, true));
  return buf;
}

describe("decodificarFotograma", () => {
  it("lee la cabecera y reparte cuerpos, productos, juntas, bandas y señales", () => {
    const f = decodificarFotograma(fotogramaBinario({
      t: 1.5, factor: 0.8,
      cuerpos: [[1, 2, 3, 0, 0, 0, 1], [4, 5, 6, 0, 0, 0, 1]],
      productos: [[NaN, NaN, NaN, NaN, NaN, NaN, NaN]],
      juntas: [90], bandas: [0.344], senales: [60, NaN, 1],
    }))!;
    expect(f.t).toBe(1.5);
    expect(f.factor).toBeCloseTo(0.8, 6);
    expect([f.nc, f.np, f.nj, f.nb, f.ns]).toEqual([2, 1, 1, 1, 3]);
    expect([...f.cuerpos.subarray(7, 10)]).toEqual([4, 5, 6]);
    expect(Number.isNaN(f.productos[0])).toBe(true);
    expect(f.juntas[0]).toBe(90);
    expect(f.bandas[0]).toBeCloseTo(0.344, 6);
    expect(f.senales[0]).toBe(60);
    expect(Number.isNaN(f.senales[1])).toBe(true);
    expect(f.senales[2]).toBe(1);
  });

  it("rechaza otro formato y un fotograma cortado", () => {
    const bueno = fotogramaBinario({ t: 1, senales: [1, 2, 3] });
    const otro = bueno.slice(0);
    new DataView(otro).setFloat32(0, 2, true);
    expect(decodificarFotograma(otro)).toBeNull();
    expect(decodificarFotograma(bueno.slice(0, bueno.byteLength - 4))).toBeNull();
    expect(decodificarFotograma(new ArrayBuffer(CABECERA * 4 - 4))).toBeNull();
  });
});

describe("leerMensaje", () => {
  it("conoce los tipos del protocolo e ignora lo demás", () => {
    expect(leerMensaje('{"tipo": "ack", "id": "a1", "t": 1.03}')).toEqual({ tipo: "ack", id: "a1", t: 1.03 });
    expect(leerMensaje('{"tipo": "senales", "desde": 123, "nombres": ["caja_0.x_mm"]}')?.tipo).toBe("senales");
    expect(leerMensaje('{"tipo": "nuevo"}')).toBeNull();
    expect(leerMensaje("no es json")).toBeNull();
    expect(leerMensaje('{"tipo": "senales", "desde": "x"}')).toBeNull();
    expect(leerMensaje('{"tipo": "inicio"}')).toBeNull(); // sin la tabla no sirve
  });
});

describe("problemaDeCierre", () => {
  it("cada código dice qué pasó y qué hacer; 4423 se puede reemplazar", () => {
    for (const c of [4401, 4403, 4409, 4400, 4423, 4500, 1006]) {
      expect(problemaDeCierre(c).texto.length).toBeGreaterThan(20);
    }
    expect(problemaDeCierre(4423).reemplazable).toBe(true);
    expect(problemaDeCierre(4400, "falta el acople", "marcha").texto).toContain("«marcha»");
    expect(problemaDeCierre(4400, "falta el acople").detalle).toBe("falta el acople");
    expect(problemaDeCierre(4409).reemplazable).toBeUndefined();
  });

  it("el fin dice por qué terminó", () => {
    expect(textoFin("parada")).toBe("Paraste la sesión.");
    expect(textoFin("reemplazada")).toContain("otra sesión");
    expect(textoFin("worker")).toContain("error");
  });
});
