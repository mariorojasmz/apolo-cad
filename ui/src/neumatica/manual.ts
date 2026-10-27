import type { Accion } from "../vivo/mandos";

/* El accionamiento manual de una electroválvula en la sesión viva (plan V8.9 D6, D12):
   `accionar_manual` con el lado («14», «12») o «0» para soltarlo, como lo valida
   `cosim/escenario.py`. Lo que está enclavado lo publica la co-simulación en la señal
   `<des>.manual` («14», «12», «14+12» o «0»): UNA fuente para el visor, el agente y otra pestaña.
   Puro. */

export function accionManual(designacion: string, lado: string): Accion {
  return { accion: "accionar_manual", dispositivo: designacion, valor: lado };
}

/** Los lados enclavados a mano según la señal `<des>.manual` (sin señal o «0», ninguno). */
export function ladosManual(senal: string | undefined): string[] {
  return senal && senal !== "0" ? senal.split("+") : [];
}

/** Los mensajes que alternan `lado` con lo que ya está puesto: el modelo suelta TODOS con «0»,
   así que soltar uno es soltar todo y volver a poner los demás. */
export function alternarManual(designacion: string, puestos: readonly string[], lado: string): Accion[] {
  if (puestos.includes(lado)) {
    return [accionManual(designacion, "0"), ...puestos.filter((x) => x !== lado).map((x) => accionManual(designacion, x))];
  }
  return [accionManual(designacion, lado)];
}

/** La posición de una electroválvula en palabras («reposo (12)», «accionada (14)», «centro (0)»,
   «lado 12» en una biestable), con el número de ISO 5599-3 entre paréntesis. `lados`: los de sus
   bobinas (el `inicio` de la sesión). */
export function posicionPersona(pos: string | undefined, lados: readonly string[]): string {
  if (pos === undefined) return "—";
  if (lados.length > 1) return pos === "0" ? "centro (0)" : `lado ${pos}`;
  return lados.includes(pos) ? `accionada (${pos})` : `reposo (${pos})`;
}

/** Dónde está la válvula, por lo que HACE (plan nombres-por-funcion D9, A4): el nombre que el
   servidor da a esa posición del carrete («Compuerta abierta»). Un nombre que es la clave misma
   (sin declarar, el servidor manda «14»: «14») no es un nombre: entonces, la posición en palabras
   («Accionada (14)»). Sin señal, null. */
export function nombrePosicion(pos: string | undefined, lados: readonly string[], estados?: Record<string, string>): string | null {
  if (pos === undefined) return null;
  const nombre = estados?.[pos];
  if (nombre && nombre !== pos) return nombre;
  const p = posicionPersona(pos, lados);
  return p.charAt(0).toUpperCase() + p.slice(1);
}

/** El rótulo del botón de un lado: «Accionar a mano» (o «Soltar») y, con dos bobinas, a qué
   posición lleva: «Accionar a mano · Compuerta abierta» (o el lado, «· 14», sin nombre). */
export function rotuloLado(lado: string, puesto: boolean, uno: boolean, estados?: Record<string, string>): string {
  const verbo = puesto ? "Soltar" : "Accionar a mano";
  return uno ? verbo : `${verbo} · ${estados?.[lado] || lado}`;
}

/** Lo enclavado a mano, en palabras: «no» o «lado 14». */
export function manualPersona(senal: string | undefined): string {
  const lados = ladosManual(senal);
  return lados.length ? `lado ${lados.join(" y ")}` : "no";
}
