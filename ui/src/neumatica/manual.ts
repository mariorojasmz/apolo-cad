import { create } from "zustand";
import type { Accion } from "../vivo/mandos";

/* El accionamiento manual de una electroválvula en la sesión viva (plan V8.9 D6, D12):
   `accionar_manual` con el lado («14», «12») o «0» para soltarlo, como lo valida
   `cosim/escenario.py`. El manual es ENCLAVADO y la co-simulación no publica una señal de él: lo
   que está puesto se lleva aquí, fuera del panel (cerrar «Mandos» y volver no lo olvida), y vale
   para UNA sesión (`inicio`). */

export function accionManual(designacion: string, lado: string): Accion {
  return { accion: "accionar_manual", dispositivo: designacion, valor: lado };
}

/** Los lados que quedan puestos de una válvula tras alternar `lado`, y los mensajes que lo hacen:
   el modelo suelta TODOS con «0», así que soltar uno es soltar todo y volver a poner los demás. */
export function alternarManual(designacion: string, puestos: readonly string[], lado: string): { quedan: string[]; acciones: Accion[] } {
  if (puestos.includes(lado)) {
    const quedan = puestos.filter((x) => x !== lado);
    return { quedan, acciones: [accionManual(designacion, "0"), ...quedan.map((x) => accionManual(designacion, x))] };
  }
  return { quedan: [...puestos, lado], acciones: [accionManual(designacion, lado)] };
}

interface EstadoManual {
  /** La sesión a la que pertenece lo puesto (el objeto `inicio`). */
  sesion: unknown;
  puestos: Record<string, string[]>;
}

export const useManual = create<EstadoManual>(() => ({ sesion: null, puestos: {} }));

/** Lo puesto de una válvula en ESTA sesión (otra sesión empieza sin nada puesto). */
export function puestosDe(st: EstadoManual, sesion: unknown, designacion: string): string[] {
  return st.sesion === sesion ? st.puestos[designacion] ?? [] : [];
}

export function ponerPuestos(sesion: unknown, designacion: string, quedan: string[]): void {
  const st = useManual.getState();
  const base = st.sesion === sesion ? st.puestos : {};
  useManual.setState({ sesion, puestos: { ...base, [designacion]: quedan } });
}
