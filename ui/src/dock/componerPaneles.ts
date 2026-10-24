import type { ComponentType } from "react";
import type { LucideIcon } from "lucide-react";
import type { AnchoPanel, Extension, IdPanelExtension } from "../extensiones/tipos";

/* Los paneles = los del núcleo + los que registran las extensiones (plan
   núcleo-abierto-extensiones-privadas, D5). Lógica pura, sin componentes reales: `paneles.ts` la
   llama con los del núcleo y vitest con unos de prueba. */

export interface PanelDef {
  /** Cabecera: pestaña de Dockview y cajón del visor. */
  titulo: string;
  /** Botón corto: StatusBar y barra de paneles del visor. */
  rotulo: string;
  Componente: ComponentType;
  icono: LucideIcon;
  /** Ancho del cajón del visor (sólo paneles de extensión; sin él, el normal). */
  ancho?: AnchoPanel;
}

export interface Paneles<N extends string> {
  paneles: Readonly<Record<N | IdPanelExtension, PanelDef>>;
  herramientas: readonly (N | IdPanelExtension)[];
}

/** Arma los paneles: primero los del núcleo (en su orden), después los de cada extensión, en el
   orden en que llegan. Un panel de extensión es herramienta salvo que diga `herramienta: false`.
   Los ids ya vienen validados por `extensiones/registro.ts` (prefijo con punto: no pisan uno del
   núcleo). */
export function componerPaneles<N extends string>(
  nucleo: Readonly<Record<N, PanelDef>>,
  herramientasNucleo: readonly N[],
  extensiones: readonly Extension[],
): Paneles<N> {
  const paneles: Record<string, PanelDef> = { ...nucleo };
  const herramientas: (N | IdPanelExtension)[] = [...herramientasNucleo];
  for (const ext of extensiones) {
    for (const p of ext.paneles ?? []) {
      paneles[p.id] = { titulo: p.titulo, rotulo: p.rotulo, Componente: p.Componente, icono: p.icono,
        ...(p.ancho ? { ancho: p.ancho } : {}) };
      if (p.herramienta !== false) herramientas.push(p.id);
    }
  }
  return { paneles: paneles as Record<N | IdPanelExtension, PanelDef>, herramientas };
}
