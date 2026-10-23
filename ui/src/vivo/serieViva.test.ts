import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { avanceCadena } from "../viewport/marcha/cadena";
import { poseProducto, tramo } from "../viewport/marcha/serie";
import { decodificarFotograma, type InicioVivo } from "./protocolo";
import { empujar, serieDesdeInicio, VENTANA_S } from "./serieViva";

/* La serie viva (plan V8.4, F0 § 4): crece en sitio, los productos NaN no se ven, la banda
   integra su recorrido, el anillo recorta de a tandas sin que la cadena salte. */

/** Un fotograma como lo empaca `cosim/vivo_fotograma.py` (sin señales). */
function fotogramaBinario(o: { t: number; cuerpos: number[][]; productos: number[][]; juntas: number[]; bandas: number[] }): ArrayBuffer {
  const datos = [1, o.t, 1, o.cuerpos.length, o.productos.length, o.juntas.length, o.bandas.length, 0,
    ...o.cuerpos.flat(), ...o.productos.flat(), ...o.juntas, ...o.bandas];
  const buf = new ArrayBuffer(datos.length * 4);
  const v = new DataView(buf);
  datos.forEach((x, i) => v.setFloat32(i * 4, x, true));
  return buf;
}

function inicio(): InicioVivo {
  return {
    tipo: "inicio", version: 1, proyecto: 77, escenario: "marcha", firma: "f", ventana_s: 1 / 30, max_s: 1800,
    ritmo: 1, dt_s: 0.002, formato: 1,
    cuerpos: [{ name: "b_j", junta: "j", piezas: ["tambor"] }],
    productos: [{ name: "p_caja_0", producto: "caja", dims_mm: [300, 200, 150] }],
    juntas: [{ name: "j", tipo: "continua", unidad: "grados" }],
    bandas: [{ pieza: "c119", junta: "j", radio_mm: 57, direccion: [1, 0, 0] }],
    senales: [], mandos: [], pilotos: [], dispositivos: [], fajas: [], cadenas: [], avisos: [],
  };
}

const fot = (t: number, q: number, v: number, caja: number[] | null) => decodificarFotograma(fotogramaBinario({
  t, cuerpos: [[0, 0, 0, 0, 0, 0, 1]], productos: [caja ?? [NaN, NaN, NaN, NaN, NaN, NaN, NaN]], juntas: [q], bandas: [v],
}))!;

describe("serie viva", () => {
  it("crece en sitio: los arreglos son los mismos objetos que guarda el reproductor", () => {
    const v = serieDesdeInicio(inicio());
    const poses = v.serie.cuerpos.b_j.poses;
    const s = v.serie.bandas[0].s_mm!;
    expect(v.serie.vivo).toBe(true);
    empujar(v, fot(0.1, 0, 0, null));
    empujar(v, fot(0.2, 10, 0.5, [100, 0, 900, 0, 0, 0, 1]));
    expect(v.serie.t).toEqual([expect.closeTo(0.1, 6), expect.closeTo(0.2, 6)]);
    expect(v.serie.cuerpos.b_j.poses).toBe(poses);
    expect(poses.length).toBe(14);
    expect(v.serie.bandas[0].s_mm).toBe(s);
    expect(s[1]).toBeCloseTo(0.5 * 0.5 * 0.1 * 1000, 2); // trapecio: 25 mm
    expect(v.serie.duracion_s).toBeCloseTo(0.2, 6);
  });

  it("una caja NaN no se ve; la misma caja con pose, sí", () => {
    const v = serieDesdeInicio(inicio());
    empujar(v, fot(0.1, 0, 0, null));
    empujar(v, fot(0.2, 0, 0, [100, 0, 900, 0, 0, 0, 1]));
    const p = v.serie.productos[0];
    const m = new THREE.Matrix4();
    expect(poseProducto(p, 0, 0, m)).toBe(false);
    expect(poseProducto(p, 0, 0.5, m)).toBe(false); // entre NaN y su primera pose: todavía no está
    expect(poseProducto(p, 1, 0, m)).toBe(true);
    expect(new THREE.Vector3().setFromMatrixPosition(m).x).toBeCloseTo(100, 3);
  });

  it("descarta un fotograma que no avanza el tiempo", () => {
    const v = serieDesdeInicio(inicio());
    empujar(v, fot(0.2, 0, 0, null));
    empujar(v, fot(0.2, 5, 0, null));
    empujar(v, fot(0.1, 5, 0, null));
    expect(v.serie.t.length).toBe(1);
  });

  it("el anillo guarda ~60 s y recorta de a tandas, sin que la cadena salte", () => {
    const v = serieDesdeInicio(inicio());
    const cadena = { junta: "j", signo: 1, z: 360 } as Parameters<typeof avanceCadena>[0];
    const dt = 1 / 30;
    let tope = 0;
    for (let k = 1; k <= 30 * 90; k++) {
      empujar(v, fot(k * dt, k, 0.3, null));
      const t = v.serie.t;
      tope = Math.max(tope, t[t.length - 1] - t[0]);
      // el avance de la cadena en la última muestra es q − q de la primera de la sesión
      const ult = tramo(t, t[t.length - 1]);
      expect(avanceCadena(cadena, v.serie, ult.i, ult.f)).toBeCloseTo(k - 1, 3);
    }
    const t = v.serie.t;
    expect(tope).toBeLessThanOrEqual(VENTANA_S * 1.25 + dt);
    expect(t[t.length - 1] - t[0]).toBeGreaterThanOrEqual(VENTANA_S - dt);
    const n = t.length;
    expect(v.serie.cuerpos.b_j.poses.length).toBe(7 * n);
    expect(v.serie.productos[0].poses.length).toBe(7 * n);
    expect(v.serie.juntas.j.q.length).toBe(n);
    expect(v.serie.juntas.j.q0).toBe(1);
    expect(v.serie.bandas[0].v_m_s.length).toBe(n);
    expect(v.serie.bandas[0].s_mm!.length).toBe(n);
    // el recorrido sigue acumulado (la textura de la faja no salta al recortar)
    expect(v.serie.bandas[0].s_mm![n - 1]).toBeCloseTo(0.3 * 1000 * (90 - dt), -1);
  });
});
