import type { ItemAtencion } from "../diseno/atencion";
import { cifra } from "../diseno/cifra";
import { MOV_NORMAL_MS, suave } from "../diseno/movimiento";
import type { CableTablero, CalentamientoTablero, ConductorTablero, ItemTablero, PanelTableroOut } from "./tipos";

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
  /** La cámara vuela a esas piezas (y a esos puntos, si los hay) y selecciona las piezas. */
  encuadrar: (piezas: readonly string[], puntos?: readonly (readonly number[])[]) => void;
  /** El ítem queda elegido: su frase de detalle aparece, y sus conductores se listan. */
  elegir: (it: ItemTablero) => void;
  /** Dibuja el recorrido de UN conductor en el 3D (null: ninguno). */
  dibujar: (conductor: string | null) => void;
}

/** Los vértices de un recorrido: lo que el encuadre tiene que mostrar entero. */
export function puntosDe(recorrido: number[][][] | null | undefined): number[][] {
  return (recorrido ?? []).flat();
}

/** Qué pasa al hacer clic en un ítem: encuadra lo que señala; un solo conductor se dibuja (y el
   encuadre lo muestra entero); varios se listan en el detalle (sin maraña de hilos, D13). */
export function alElegir(it: ItemTablero, a: AccionesTablero, panel?: PanelTableroOut | null): void {
  a.elegir(it);
  const uno = it.conductores.length === 1 ? it.conductores[0] : null;
  a.dibujar(uno);
  const puntos = puntosDe(recorridoDe(panel ?? null, uno));
  if (it.piezas.length || puntos.length) a.encuadrar(it.piezas, puntos.length ? puntos : undefined);
}

/** Los ítems del servidor como filas de `<ItemsAtencion>`: con acción si señalan algo o tienen
   algo más que decir. */
export function itemsDeAtencion(items: readonly ItemTablero[], a: AccionesTablero,
  panel?: PanelTableroOut | null): ItemAtencion[] {
  return items.map((it) => ({
    clave: it.clave,
    severidad: it.severidad,
    frase: it.frase,
    cifra: cifraDe(it),
    accion: it.piezas.length || it.conductores.length || it.detalle ? () => alElegir(it, a, panel) : undefined,
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

/** El recorrido de un conductor o de un cable de campo para dibujarlo (comparten los ids: son
   comandos), o null (sin recorrido o sin elegido). */
export function recorridoDe(panel: PanelTableroOut | null, id: string | null): number[][][] | null {
  if (!panel || !id) return null;
  const c = panel.detalle?.conductores.find((x) => x.id === id) ?? panel.detalle?.cables?.find((x) => x.id === id);
  return c?.recorrido?.length ? c.recorrido : null;
}

/** Los cables de campo del detalle: todos, o sólo los del ítem elegido. */
export function cablesListados(panel: PanelTableroOut, filtro: readonly string[] | null): CableTablero[] {
  const todos = panel.detalle?.cables ?? [];
  if (!filtro || !filtro.length) return todos;
  const quiero = new Set(filtro);
  return todos.filter((c) => quiero.has(c.id));
}

/** El largo de un cable de campo («4,57 m»), o nada si no se calculó. */
export function largoCable(c: CableTablero): string | undefined {
  return c.largo_m === undefined ? undefined : cifra(c.largo_m, 2, "m");
}

/** La segunda línea de un cable: de qué sale su largo, el puesto a mano o que está incompleto. */
export function partesCable(c: CableTablero): string {
  const partes: string[] = [];
  if (c.incompleto) partes.push("Recorrido incompleto");
  if (c.partes_m) {
    const p = c.partes_m;
    partes.push(`Dentro ${cifra(p.adentro, 2, "m")} · afuera ${cifra(p.afuera, 2, "m")} · reserva ${cifra(p.reserva, 2, "m")}`);
  }
  if (c.declarado_m !== undefined) partes.push(`Puesto a mano: ${cifra(c.declarado_m, 2, "m")}`);
  return partes.join(" · ");
}

/** Los supuestos del recorrido: los del tablero y, con su designación, los de cada cable. */
export function supuestosDe(panel: PanelTableroOut): string[] {
  const d = panel.detalle;
  if (!d) return [];
  const cables = (d.cables ?? []).flatMap((c) =>
    (c.supuestos ?? []).map((s) => (s.startsWith(c.designacion) ? s : `${c.designacion}: ${s}`)));
  return [...new Set([...d.supuestos, ...cables])];
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

/** Las pérdidas declaradas, en una frase con su cifra. */
export function perdidasDeclaradas(perdidas: number, sinDato: readonly string[]): string {
  const base = `Pérdidas declaradas de los aparatos: ${cifra(perdidas, 0, "W")}`;
  if (!sinDato.length) return base;
  return `${base} (${sinDato.length} ${sinDato.length === 1 ? "aparato no trae" : "aparatos no traen"} el dato)`;
}

/** Las filas del calentamiento evaluado (rótulo, cifra); vacía si quedó sin evaluar. */
export function filasCalor(c: CalentamientoTablero): [string, string][] {
  if (c.estado === "sin_evaluar" || c.T_arriba_C === undefined) return [];
  const filas: [string, string][] = [];
  if (c.T_media_C !== undefined) filas.push(["A media altura", cifra(c.T_media_C, 0, "°C")]);
  filas.push(["Arriba", cifra(c.T_arriba_C, 0, "°C")]);
  if (c.peor) filas.push([`Admite ${c.peor.designacion}`, cifra(c.peor.T_max_C, 0, "°C")]);
  if (c.ambiente_C !== undefined) filas.push(["Ambiente", cifra(c.ambiente_C, 0, "°C")]);
  if (c.ventilacion_m3h) filas.push(["Ventilador", cifra(c.ventilacion_m3h, 0, "m³/h")]);
  return filas;
}

/** Las pérdidas del calentamiento: total y de dónde salen (aparatos y conductores). */
export function perdidasCalor(c: CalentamientoTablero): string {
  if (!c.perdidas) return perdidasDeclaradas(c.perdidas_W, c.sin_dato);
  const base = `Pierde ${cifra(c.perdidas_W, 0, "W")}: ${cifra(c.perdidas.aparatos_W, 0, "W")} los aparatos y `
    + `${cifra(c.perdidas.conductores_W, 0, "W")} los conductores`;
  if (!c.sin_dato.length) return base;
  return `${base} (${c.sin_dato.length} ${c.sin_dato.length === 1 ? "aparato no trae" : "aparatos no traen"} el dato)`;
}
