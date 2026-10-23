import type { BandaSerie, CuerpoSerie, SerieMarcha } from "../viewport/marcha/serie";
import type { Fotograma, InicioVivo } from "./protocolo";

/* La serie de la máquina viva (plan V8.4, F0 § 4): una `SerieMarcha` como la de «Ver la marcha»
   que CRECE fotograma a fotograma y se recorta en un anillo de ~60 s. El reproductor de la marcha
   la lee igual que una serie calculada (cuerpos relativos, productos absolutos, juntas, bandas);
   por eso se muta EN SITIO: el reproductor, la faja y las cadenas guardan referencias a estos
   arreglos al armarse y nunca se rehacen por fotograma.
   - Productos: `desde` 0 y una pose por muestra, NaN cuando la caja no está en el mundo.
   - Bandas: además de `v_m_s`, el recorrido acumulado `s_mm` (la faja corre su textura con él).
   - Juntas: al recortar, `q0` guarda la q de la primera muestra de la sesión (la cadena avanza
     desde ahí y no salta). */

/** Lo que el anillo guarda (s). Se recorta de a tandas: al pasar `VENTANA_S · HOLGURA`. */
export const VENTANA_S = 60;
const HOLGURA = 1.25;

export interface SerieViva {
  serie: SerieMarcha;
  /** Los cuerpos, juntas y bandas en el ORDEN del fotograma. */
  cuerpos: CuerpoSerie[];
  juntas: { q: number[]; q0?: number }[];
  bandas: (BandaSerie & { s_mm: number[] })[];
}

export function serieDesdeInicio(ini: InicioVivo): SerieViva {
  const cuerpos: CuerpoSerie[] = ini.cuerpos.map((c) => ({ junta: c.junta, piezas: [...c.piezas], poses: [] }));
  const juntas = ini.juntas.map((j) => ({ tipo: j.tipo, unidad: j.unidad, q: [] as number[] }));
  const bandas = ini.bandas.map((b) => ({ ...b, v_m_s: [] as number[], s_mm: [] as number[] }));
  const serie: SerieMarcha = {
    hz: 30,
    duracion_s: 0,
    t: [],
    cuerpos: Object.fromEntries(ini.cuerpos.map((c, k) => [c.name, cuerpos[k]])),
    productos: ini.productos.map((p) => ({ ...p, dims_mm: [...p.dims_mm] as [number, number, number], desde: 0, poses: [] })),
    juntas: Object.fromEntries(ini.juntas.map((j, k) => [j.name, juntas[k]])),
    bandas,
    fajas: ini.fajas ?? [],
    cadenas: ini.cadenas ?? [],
    resumen: {},
    avisos: [...(ini.avisos ?? [])],
    firma: ini.firma,
    escenario: ini.escenario,
    vivo: true,
  };
  return { serie, cuerpos, juntas, bandas };
}

function copiar(dst: number[], src: Float32Array, desde: number, n: number): void {
  for (let k = 0; k < n; k++) dst.push(src[desde + k]);
}

/** Suma un fotograma a la serie. Uno que no avanza el tiempo se descarta. */
export function empujar(v: SerieViva, f: Fotograma, ventana_s = VENTANA_S): void {
  const { serie } = v;
  const n = serie.t.length;
  const tPrev = n ? serie.t[n - 1] : null;
  if (tPrev !== null && !(f.t > tPrev)) return;
  serie.t.push(f.t);
  v.cuerpos.forEach((c, k) => {
    if (k < f.nc) copiar(c.poses, f.cuerpos, 7 * k, 7);
    else c.poses.push(0, 0, 0, 0, 0, 0, 1); // fotograma corto: el cuerpo queda en su pose de diseño
  });
  serie.productos.forEach((p, k) => {
    if (k < f.np) copiar(p.poses, f.productos, 7 * k, 7);
    else p.poses.push(NaN, NaN, NaN, NaN, NaN, NaN, NaN);
  });
  v.juntas.forEach((j, k) => {
    const q = k < f.nj ? f.juntas[k] : NaN;
    j.q.push(Number.isFinite(q) ? q : j.q.length ? j.q[j.q.length - 1] : 0);
  });
  v.bandas.forEach((b, k) => {
    const vel = k < f.nb && Number.isFinite(f.bandas[k]) ? f.bandas[k] : 0;
    const m = b.v_m_s.length;
    const s = m && tPrev !== null ? b.s_mm[m - 1] + 0.5 * (vel + b.v_m_s[m - 1]) * (f.t - tPrev) * 1000 : 0;
    b.v_m_s.push(vel);
    b.s_mm.push(s);
  });
  serie.duracion_s = f.t;
  recortar(v, ventana_s);
}

/** Deja la última `ventana_s` (de a tandas, para no mover los arreglos en cada fotograma). */
export function recortar(v: SerieViva, ventana_s = VENTANA_S): void {
  const { t } = v.serie;
  const n = t.length;
  if (n < 2 || t[n - 1] - t[0] <= ventana_s * HOLGURA) return;
  const desde = t[n - 1] - ventana_s;
  let k = 0;
  while (k < n - 1 && t[k] < desde) k++;
  if (k === 0) return;
  t.splice(0, k);
  for (const c of v.cuerpos) c.poses.splice(0, 7 * k);
  for (const p of v.serie.productos) p.poses.splice(0, 7 * k);
  for (const j of v.juntas) {
    if (j.q0 === undefined && j.q.length) j.q0 = j.q[0];
    j.q.splice(0, k);
  }
  for (const b of v.bandas) {
    b.v_m_s.splice(0, k);
    b.s_mm.splice(0, k);
  }
}
