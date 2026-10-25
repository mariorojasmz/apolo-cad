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
