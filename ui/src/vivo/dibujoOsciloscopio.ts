import { escalaDe, ticksTiempo, type Fuente } from "./osciloscopio";
import { leerValor, type Medida } from "./unidades";

/* El dibujo del osciloscopio en un canvas 2D (plan V8.4 D6; F0 midió 0,2–0,6 ms por cuadro con
   8 señales y 60 s). UN CARRIL POR SEÑAL, apilados con el eje de tiempo común: cada señal con
   su propia escala sin ejes dobles. Cada carril lleva su rótulo (muestra de color + nombre +
   valor, en la tinta del tema: el texto nunca va en el color de la serie), su escala a la derecha
   y la curva de 2 px. Con más muestras que píxeles, se dibuja el mínimo y el máximo de cada
   columna. El disparo: línea vertical en su instante y el umbral punteado en su carril. */

export interface Tinta {
  texto: string;
  tenue: string;
  linea: string;
  fondo: string;
}

export interface Carril {
  senal: string;
  color: string;
  medida: Medida;
}

export interface OpcionesDibujo {
  disparo?: { senal: string; umbral: number; t: number | null } | null;
  /** x del puntero (px CSS) para la cruz y los valores en ese instante. */
  punteroX?: number | null;
}

const EJE = 18; // alto del eje de tiempo
const SEP = 2; // separación entre carriles
const FUENTE = "11px system-ui, -apple-system, 'Segoe UI', sans-serif";
const FUENTE_CHICA = "10px system-ui, -apple-system, 'Segoe UI', sans-serif";

/** La muestra más cercana a `t` (índice), o -1. */
function cercana(f: Fuente, t: number, k0: number, k1: number): number {
  if (k1 <= k0) return -1;
  const k = Math.min(Math.max(f.desde(t), k0), k1 - 1);
  if (k > k0 && Math.abs(f.tEn(k - 1) - t) < Math.abs(f.tEn(k) - t)) return k - 1;
  return k;
}

function valorCercano(f: Fuente, senal: string, k: number, k0: number): number {
  for (let j = k; j >= k0; j--) {
    const v = f.valor(senal, j);
    if (Number.isFinite(v)) return v;
  }
  return NaN;
}

export function dibujarOsciloscopio(
  ctx: CanvasRenderingContext2D, ancho: number, alto: number, dpr: number,
  f: Fuente, carriles: readonly Carril[], t0: number, t1: number, tinta: Tinta, op: OpcionesDibujo = {},
): void {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, ancho, alto);
  if (!carriles.length || !(t1 > t0)) return;
  const n = carriles.length;
  const altoCarril = (alto - EJE - SEP * (n - 1)) / n;
  if (altoCarril < 8) return;
  const xDe = (t: number) => ((t - t0) / (t1 - t0)) * ancho;
  // margen de una muestra a cada lado: la curva entra y sale por el borde
  const k0 = Math.max(0, f.desde(t0) - 1);
  const k1 = Math.min(f.n, f.desde(t1) + 1);
  const tPuntero = op.punteroX != null ? t0 + (op.punteroX / ancho) * (t1 - t0) : null;
  const kPuntero = tPuntero !== null ? cercana(f, tPuntero, k0, k1) : -1;

  // eje de tiempo y rejilla vertical tenue
  ctx.font = FUENTE_CHICA;
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  for (const t of ticksTiempo(t0, t1)) {
    const x = Math.round(xDe(t)) + 0.5;
    ctx.strokeStyle = tinta.linea;
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, alto - EJE);
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.fillStyle = tinta.tenue;
    ctx.fillText(`${String(Math.round(t * 10) / 10).replace(".", ",")} s`, Math.min(Math.max(x, 16), ancho - 16), alto - EJE / 2);
  }

  carriles.forEach((c, i) => {
    const top = i * (altoCarril + SEP);
    const bot = top + altoCarril;
    const pad = Math.min(16, altoCarril * 0.22);
    const e = escalaDe(f, c.senal, k0, k1, c.medida.booleana);
    const yDe = (v: number) => bot - 4 - ((v - e.lo) / (e.hi - e.lo)) * (altoCarril - 4 - pad);
    // separador del carril
    ctx.strokeStyle = tinta.linea;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, Math.round(bot) + 0.5);
    ctx.lineTo(ancho, Math.round(bot) + 0.5);
    ctx.stroke();
    // umbral del disparo
    const disp = op.disparo;
    if (disp && disp.senal === c.senal && Number.isFinite(disp.umbral)) {
      const y = Math.round(yDe(disp.umbral)) + 0.5;
      if (y > top && y < bot) {
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = tinta.tenue;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(ancho, y);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
    // la curva (min/máx por columna si hay más muestras que píxeles)
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, top, ancho, altoCarril);
    ctx.clip();
    ctx.strokeStyle = c.color;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.beginPath();
    const muestras = k1 - k0;
    if (muestras > ancho * 2) {
      let col = -1;
      let mn = Infinity;
      let mx = -Infinity;
      const volcar = () => {
        if (col < 0 || mn > mx) return;
        ctx.moveTo(col + 0.5, yDe(mx));
        ctx.lineTo(col + 0.5, yDe(mn) + 0.01);
      };
      for (let k = k0; k < k1; k++) {
        const v = f.valor(c.senal, k);
        const x = Math.floor(xDe(f.tEn(k)));
        if (x !== col) {
          volcar();
          col = x;
          mn = Infinity;
          mx = -Infinity;
        }
        if (Number.isFinite(v)) {
          mn = Math.min(mn, v);
          mx = Math.max(mx, v);
        }
      }
      volcar();
    } else {
      let abierto = false;
      for (let k = k0; k < k1; k++) {
        const v = f.valor(c.senal, k);
        if (!Number.isFinite(v)) {
          abierto = false; // un hueco corta la curva
          continue;
        }
        const x = xDe(f.tEn(k));
        const y = yDe(v);
        if (abierto) ctx.lineTo(x, y);
        else ctx.moveTo(x, y);
        abierto = true;
      }
    }
    ctx.stroke();
    ctx.restore();
    // rótulo: muestra de color + nombre + valor (el del puntero o el último)
    const kv = kPuntero >= 0 ? kPuntero : k1 - 1;
    const v = kv >= k0 ? valorCercano(f, c.senal, kv, k0) : NaN;
    ctx.font = FUENTE;
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillStyle = c.color;
    ctx.fillRect(6, top + 5, 8, 8);
    const rotulo = `${c.senal}  ${leerValor(v, c.medida)}`;
    const wr = ctx.measureText(rotulo).width;
    ctx.fillStyle = tinta.fondo;
    ctx.globalAlpha = 0.75;
    ctx.fillRect(17, top + 2, wr + 6, 14);
    ctx.globalAlpha = 1;
    ctx.fillStyle = tinta.texto;
    ctx.fillText(rotulo, 20, top + 3);
    // escala a la derecha (una por señal)
    if (!c.medida.booleana && altoCarril >= 34) {
      ctx.font = FUENTE_CHICA;
      ctx.textAlign = "right";
      ctx.fillStyle = tinta.tenue;
      const sinUnidad = { ...c.medida, unidad: "" };
      ctx.textBaseline = "top";
      ctx.fillText(leerValor(e.hi, sinUnidad), ancho - 4, top + 3);
      ctx.textBaseline = "bottom";
      ctx.fillText(leerValor(e.lo, sinUnidad), ancho - 4, bot - 2);
    }
    // punto del puntero
    if (kPuntero >= 0 && Number.isFinite(v)) {
      ctx.fillStyle = c.color;
      ctx.strokeStyle = tinta.fondo;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(xDe(f.tEn(kPuntero)), yDe(v), 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
  });

  // instante del disparo
  const td = op.disparo?.t;
  if (td != null && td >= t0 && td <= t1) {
    const x = Math.round(xDe(td)) + 0.5;
    ctx.setLineDash([5, 3]);
    ctx.strokeStyle = tinta.texto;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, alto - EJE);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  // cruz del puntero
  if (kPuntero >= 0) {
    const x = Math.round(xDe(f.tEn(kPuntero))) + 0.5;
    ctx.strokeStyle = tinta.tenue;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, alto - EJE);
    ctx.stroke();
  }
}
