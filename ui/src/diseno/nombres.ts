/* El nombre de un aparato para la persona (plan nombres-por-funcion D3, D9, D13): lo que HACE
   manda y la designación va detrás, chica. El rótulo lo da el servidor (`rotulo` en el `inicio` del
   vivo, en «Tablero», en «Neumática»); sin él (un servidor anterior) lo principal es la designación
   y nunca una tabla de tipos de la UI. Lo comparten «Mandos», «Tablero», «Neumática», «Señales» y
   la ficha de pieza. Puro (se prueba en node). */

export interface ConNombre {
  designacion: string;
  /** «Marcha», «Tapa del tanque»: lo que hace, como en su placa. */
  rotulo?: string;
}

/** Lo principal: el rótulo; sin él, la designación (lo único que dijo el servidor). */
export function nombrePrincipal(a: ConNombre): string {
  return a.rotulo || a.designacion;
}

/** La designación va detrás, chica, sólo si el rótulo ocupa lo principal. */
export function designacionSecundaria(a: ConNombre): string | null {
  return a.rotulo ? a.designacion : null;
}

/** Lo que va detrás del nombre: la designación (si el rótulo manda) y un detalle («Relé de
 *  seguridad 2 canales», «Ø32 mm · carrera 200 mm»), sin repetir lo principal. */
export function partesSecundarias(a: ConNombre, detalle?: string | null): string[] {
  const principal = nombrePrincipal(a);
  return [designacionSecundaria(a), detalle && detalle !== principal ? detalle : null]
    .filter((x): x is string => !!x);
}

/** Una junta se nombra por su pieza HIJA (D15): el nombre que esa pieza tiene en la escena (del
   servidor), con el id de la junta detrás; sin pieza hija conocida, el id solo. */
export function nombreDeJunta(j: { name: string; child: string }, nombreDePieza: (id: string) => string): ConNombre {
  const hija = nombreDePieza(j.child);
  return hija && hija !== j.child ? { designacion: j.name, rotulo: hija } : { designacion: j.name };
}

/** El nombre DENTRO de una frase («contacto soldado en el contactor»): el `en_frase` del servidor
 *  (minúscula y artículo: el género lo decide él, F5b); sin él, el rótulo en minúscula (una sigla
 *  queda) o, sin rótulo, la designación. */
export function nombreEnFrase(a: ConNombre & { en_frase?: string }): string {
  if (a.en_frase) return a.en_frase;
  const r = a.rotulo;
  if (!r) return a.designacion;
  return r.length > 1 && r[1] === r[1].toUpperCase() && r[1] !== r[1].toLowerCase() ? r : r[0].toLowerCase() + r.slice(1);
}

/** «Marcha · -S1»: el nombre en una línea de texto (un `aria-label`, una opción). */
export function nombreEnLinea(a: ConNombre, detalle?: string | null): string {
  return [nombrePrincipal(a), ...partesSecundarias(a, detalle)].join(" · ");
}
