/* El área del visor que de verdad se ve (plan visor-para-evaluar D13): el lienzo menos lo que lo
   tapa de lado a lado (los cajones del visor, que flotan ENCIMA del canvas). Todo encuadre la usa
   para centrar y medir: una pieza encuadrada detrás del panel lateral no se ve. Lo que tapa se
   marca con el atributo `TAPA_VISTA`; aquí no se nombra ningún panel. Puro salvo `areaLibreDe`. */

/** Atributo de un elemento flotante que tapa el visor (un cajón): el encuadre lo descuenta. */
export const TAPA_VISTA = "data-tapa-vista";

export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** Un rectángulo en coordenadas normalizadas de la cámara (−1…1, y hacia arriba). */
export interface AreaNdc {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

export const AREA_COMPLETA: AreaNdc = { x0: -1, x1: 1, y0: -1, y1: 1 };

/** Lo libre del lienzo: cada tapa que ocupa al menos `alturaMin` de su alto y toca su mitad
   izquierda o derecha recorta ese lado. Una tapa chica (un menú, una ficha) no cuenta: correr la
   cámara por ella movería todo por poco. Si lo libre quedara más angosto que `anchoMin` del
   lienzo, se queda el lienzo entero (pantalla angosta con el cajón encima: no hay dónde centrar). */
export function areaLibre(lienzo: Rect, tapas: readonly Rect[], alturaMin = 0.5, anchoMin = 0.3): Rect {
  const ancho = lienzo.right - lienzo.left, alto = lienzo.bottom - lienzo.top;
  if (!(ancho > 0) || !(alto > 0)) return lienzo;
  let izq = lienzo.left, der = lienzo.right;
  const medio = (lienzo.left + lienzo.right) / 2;
  for (const t of tapas) {
    const solapeV = Math.min(t.bottom, lienzo.bottom) - Math.max(t.top, lienzo.top);
    const solapeH = Math.min(t.right, lienzo.right) - Math.max(t.left, lienzo.left);
    if (solapeV < alto * alturaMin || solapeH <= 0) continue;
    if ((t.left + t.right) / 2 < medio) izq = Math.max(izq, Math.min(t.right, lienzo.right));
    else der = Math.min(der, Math.max(t.left, lienzo.left));
  }
  if (der - izq < ancho * anchoMin) return lienzo;
  return { left: izq, top: lienzo.top, right: der, bottom: lienzo.bottom };
}

/** `libre` (px de pantalla) dentro de `lienzo`, en coordenadas normalizadas de la cámara. */
export function aNdc(lienzo: Rect, libre: Rect): AreaNdc {
  const w = lienzo.right - lienzo.left, h = lienzo.bottom - lienzo.top;
  if (!(w > 0) || !(h > 0)) return AREA_COMPLETA;
  const x = (px: number) => ((px - lienzo.left) / w) * 2 - 1;
  const y = (py: number) => 1 - ((py - lienzo.top) / h) * 2;
  return { x0: x(libre.left), x1: x(libre.right), y0: y(libre.bottom), y1: y(libre.top) };
}

/** El área libre del canvas `el` con lo que hoy lo tapa (`[data-tapa-vista]` del documento). */
export function areaLibreDe(el: Element, raiz: ParentNode = document): AreaNdc {
  const r = el.getBoundingClientRect();
  const lienzo = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
  const tapas = Array.from(raiz.querySelectorAll(`[${TAPA_VISTA}]`)).map((t) => {
    const b = t.getBoundingClientRect();
    return { left: b.left, top: b.top, right: b.right, bottom: b.bottom };
  });
  return aNdc(lienzo, areaLibre(lienzo, tapas));
}
