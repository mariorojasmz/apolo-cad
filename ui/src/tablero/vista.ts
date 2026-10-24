import type { ItemAtencion } from "../diseno/atencion";
import { cifra } from "../diseno/cifra";
import { MOV_NORMAL_MS, suave } from "../diseno/movimiento";
import type { ConductorTablero, ItemTablero, PanelTableroOut } from "./tipos";

/* La lógica pura del panel «Tablero» (plan V8.5 D13): de lo que manda el servidor a lo que se
   dibuja. Ninguna regla de ingeniería vive aquí (las decide `services/tablero_panel.py`): sólo
   cómo se escribe una cifra, qué hace el clic de cada ítem, qué conductores se listan y cómo se
   anima la puerta. */

/** La cifra de un ítem, ya escrita («64 %», «10 conductores», «110°»), o nada. */
export function cifraDe(it: Pick<ItemTablero, "valor" | "unidad" | "decimales">): string | undefined {
  return it.valor === undefined ? undefined : cifra(it.valor, it.decimales ?? 0, it.unidad ?? "");
}

/** Lo que hace el clic en un ítem. */
export interface AccionesTablero {
  /** La cámara vuela a esas piezas y las selecciona. */
  encuadrar: (piezas: readonly string[]) => void;
  /** El ítem queda elegido: su frase de detalle aparece, y sus conductores se listan. */
  elegir: (it: ItemTablero) => void;
  /** Dibuja el recorrido de UN conductor en el 3D (null: ninguno). */
  dibujar: (conductor: string | null) => void;
}

/** Qué pasa al hacer clic en un ítem: encuadra lo que señala; un solo conductor se dibuja;
   varios se listan en el detalle (no hay maraña de hilos en el 3D, D13). */
export function alElegir(it: ItemTablero, a: AccionesTablero): void {
  a.elegir(it);
  a.dibujar(it.conductores.length === 1 ? it.conductores[0] : null);
  if (it.piezas.length) a.encuadrar(it.piezas);
}

/** Los ítems del servidor como filas de `<ItemsAtencion>`: con acción si señalan algo o tienen
   algo más que decir. */
export function itemsDeAtencion(items: readonly ItemTablero[], a: AccionesTablero): ItemAtencion[] {
  return items.map((it) => ({
    clave: it.clave,
    severidad: it.severidad,
    frase: it.frase,
    cifra: cifraDe(it),
    accion: it.piezas.length || it.conductores.length || it.detalle ? () => alElegir(it, a) : undefined,
  }));
}

/** Los conductores del detalle: todos, o sólo los del ítem elegido (en su orden). */
export function conductoresListados(panel: PanelTableroOut, filtro: readonly string[] | null): ConductorTablero[] {
  const todos = panel.detalle?.conductores ?? [];
  if (!filtro || !filtro.length) return todos;
  const quiero = new Set(filtro);
  return todos.filter((c) => quiero.has(c.id));
}

/** «-F1:2 → -T2:L1»: los bornes de un conductor, como se leen en el plano. */
export function rotuloConductor(c: Pick<ConductorTablero, "puntos">): string {
  return c.puntos.join(" → ");
}

/** El largo de un conductor y, si es el escrito a mano, que lo es. */
export function largoConductor(c: ConductorTablero): string {
  return cifra(c.largo_m, 2, "m");
}

/** El recorrido de un conductor para dibujarlo, o null (sin recorrido o sin conductor). */
export function recorridoDe(panel: PanelTableroOut | null, id: string | null): number[][][] | null {
  if (!panel || !id) return null;
  const c = panel.detalle?.conductores.find((x) => x.id === id);
  return c?.recorrido?.length ? c.recorrido : null;
}

/** El valor de la puerta en la fracción `f` del tiempo de su animación, con la curva suave. */
export function valorPuertaEn(desde: number, hasta: number, f: number): number {
  return desde + (hasta - desde) * suave(Math.min(1, Math.max(0, f)));
}

/** Cuánto dura abrir o cerrar la puerta (la de `--mov-normal`; 0 con movimiento reducido). */
export function duracionPuerta(reducido: boolean): number {
  return reducido ? 0 : MOV_NORMAL_MS;
}

/** El texto del botón de la puerta: abre si está casi cerrada, cierra si no. */
export function accionPuerta(valor: number, max: number): { rotulo: string; destino: number } {
  return valor < max / 2 ? { rotulo: "Abrir", destino: max } : { rotulo: "Cerrar", destino: 0 };
}

/** Las pérdidas declaradas, en una frase con su cifra (el calentamiento sigue sin evaluar). */
export function perdidasDeclaradas(perdidas: number, sinDato: readonly string[]): string {
  const base = `Pérdidas declaradas de los aparatos: ${cifra(perdidas, 0, "W")}`;
  if (!sinDato.length) return base;
  return `${base} (${sinDato.length} ${sinDato.length === 1 ? "aparato no trae" : "aparatos no traen"} el dato)`;
}
