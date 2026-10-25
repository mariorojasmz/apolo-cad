import type { ComponentType } from "react";
import type { LucideIcon } from "lucide-react";
import type { DispositivoVivo, InicioVivo } from "../vivo/protocolo";

/* Contrato de una extensión de la UI (plan núcleo-abierto-extensiones-privadas, D5). La UI se
   compone al COMPILAR: una extensión es una carpeta `src/extensiones/<nombre>/` copiada dentro de
   un checkout del núcleo, con un `index.ts` cuyo `export default` es un objeto `Extension`. El
   núcleo no la nombra: la recoge `registro.ts` con `import.meta.glob`.

   Crece SIN romper: lo nuevo entra como campo OPCIONAL (p. ej. secciones de un panel del núcleo),
   y una extensión que no lo declara sigue valiendo. Hoy hay paneles (con su ancho), chips de la
   barra viva y pantallas 3D (plan plc-en-el-lazo, D13); la sesión viva se lee y se maneja con la
   API declarada de `extensiones/vivo.ts`, nunca importando `vivo/` por ruta relativa. */

/** Id de un panel de extensión: `<nombre de la extensión>.<panel>` (p. ej. `hola.saludo`). El
   prefijo evita chocar con un panel del núcleo, cuyos ids nunca llevan punto. */
export type IdPanelExtension = `${string}.${string}`;

/** Ancho que pide un panel en el cajón del visor. `"lamina"`: el de una lámina en SVG (un
   esquema, un plano), `min(960 px, todo el visor)` en vez de los 400 px del cajón (plan
   puntos-de-extension-entregables, D7). En Completo no cambia nada: los paneles-herramienta
   ya van debajo del viewport, a todo el ancho. */
export type AnchoPanel = "lamina";

export const ANCHOS_PANEL: readonly AnchoPanel[] = ["lamina"];

export interface PanelDeExtension {
  id: IdPanelExtension;
  /** Cabecera: pestaña de Dockview y cajón del visor. */
  titulo: string;
  /** Botón corto: StatusBar y barra de paneles del visor. */
  rotulo: string;
  Componente: ComponentType;
  icono: LucideIcon;
  /** Se conmuta desde la StatusBar y desde «Más» del visor. Por defecto, sí. */
  herramienta?: boolean;
  /** Sin él, el ancho normal del cajón. */
  ancho?: AnchoPanel;
}

/** Id de un chip o una pantalla de extensión: `<nombre de la extensión>.<punto>`, como un panel. */
export type IdPuntoExtension = `${string}.${string}`;

/** Un chip de la barra de la sesión viva (plan plc-en-el-lazo, D13 a): va tras la fase y el factor
   de tiempo real, en el orden de las extensiones y de su lista. Lee la sesión con la API de
   `extensiones/vivo.ts` (`useFaseVivo`, `useValorVivo`…); un chip que revienta no tumba la barra. */
export interface ChipVivo {
  id: IdPuntoExtension;
  Componente: ComponentType;
}

/** Los colores y la letra del tema para pintar en un canvas (sólo tokens de `styles.css`). */
export interface TemaPantalla {
  fondo: string;
  panel: string;
  texto: string;
  tenue: string;
  acento: string;
  borde: string;
  fuente: string;
}

/** Un mensaje de una extensión a la sesión viva: una acción (`{accion: "escribir", dispositivo,
   variable, valor}`, `{accion: "pulsar", dispositivo}`…) o un evento (`{evento: {...}}`). Nunca un
   control (pausar, parar): esos son de la persona. El id lo pone el núcleo. */
export type MensajeExtension = { accion: string; [clave: string]: unknown } | { evento: Record<string, unknown> };

/** Lo que una pantalla 3D ve de la sesión viva cuando pinta o la tocan. */
export interface VivoPantalla {
  /** El dispositivo de la tabla del `inicio` que lleva esta pantalla (designación, ref, pieza). */
  dispositivo: DispositivoVivo;
  inicio: InicioVivo;
  /** El tamaño del canvas en píxeles (`pantalla_px` del dispositivo). */
  ancho: number;
  alto: number;
  /** Tiempo virtual del último fotograma (s). */
  t: number;
  valor: (senal: string) => number | undefined;
  texto: (senal: string) => string | undefined;
  /** Manda una acción o un evento; `false` si no salió (sin sesión, o el mensaje no vale). */
  enviar: (mensaje: MensajeExtension) => boolean;
  tema: TemaPantalla;
  /** `prefers-reduced-motion`: sin transiciones ni destellos al pintar. */
  movimientoReducido: boolean;
}

/** Una pantalla pintada sobre la pieza 3D de cada dispositivo de la sesión con ese `tipo` (plan
   plc-en-el-lazo, D13 b): un plano con su canvas sobre la cara frontal de la pieza, a la resolución
   del dispositivo. `dibujar` se llama ≈ 10 veces por segundo; `tocar` recibe el punto tocado en
   píxeles del canvas (origen arriba a la izquierda). Sin `tocar`, el clic pasa al visor. */
export interface Pantalla3D {
  id: IdPuntoExtension;
  /** El `tipo` del dispositivo en la tabla del `inicio` (p. ej. `hmi`). */
  tipo: string;
  dibujar: (ctx: CanvasRenderingContext2D, vivo: VivoPantalla) => void;
  tocar?: (x: number, y: number, vivo: VivoPantalla) => void;
}

export interface Extension {
  /** El nombre de la carpeta (`src/extensiones/<nombre>/`) y el prefijo de sus ids. */
  nombre: string;
  paneles?: readonly PanelDeExtension[];
  /** Chips de la barra de la sesión viva. */
  chipsVivo?: readonly ChipVivo[];
  /** Pantallas sobre las piezas 3D de la sesión viva. */
  pantallas3d?: readonly Pantalla3D[];
}
