import type { ComponentType } from "react";
import type { LucideIcon } from "lucide-react";

/* Contrato de una extensión de la UI (plan núcleo-abierto-extensiones-privadas, D5). La UI se
   compone al COMPILAR: una extensión es una carpeta `src/extensiones/<nombre>/` copiada dentro de
   un checkout del núcleo, con un `index.ts` cuyo `export default` es un objeto `Extension`. El
   núcleo no la nombra: la recoge `registro.ts` con `import.meta.glob`.

   Crece SIN romper: lo nuevo entra como campo OPCIONAL (p. ej. secciones de un panel del núcleo),
   y una extensión que no lo declara sigue valiendo. Hoy sólo hay paneles (con su ancho). */

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

export interface Extension {
  /** El nombre de la carpeta (`src/extensiones/<nombre>/`) y el prefijo de sus ids. */
  nombre: string;
  paneles?: readonly PanelDeExtension[];
}
