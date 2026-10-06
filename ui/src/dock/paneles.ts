import type { ComponentType } from "react";

import Tree from "../panels/Tree";
import Properties from "../panels/Properties";
import ChatPanel from "../chat/ChatPanel";
import HistoryPanel from "../panels/HistoryPanel";
import RequirementsPanel from "../panels/RequirementsPanel";
import BomPanel from "../panels/BomPanel";
import ChecksPanel from "../panels/ChecksPanel";
import KinematicsPanel from "../panels/KinematicsPanel";
import MatesPanel from "../panels/MatesPanel";
import PhysicsPanel from "../panels/PhysicsPanel";
import AssemblyPanel from "../panels/AssemblyPanel";
import SketchBlockPanel from "../panels/SketchBlockPanel";

/* Los paneles de Apolo, una sola vez: el mismo componente lo monta Dockview en Completo
   (`DockShell.tsx`) y un cajón en el visor (`visor/Cajon.tsx`, plan modo-visor D3). El
   viewport no está aquí: es el centro fijo del dock y nunca va en un cajón.
   `titulo` = cabecera (pestaña de Dockview, cajón); `rotulo` = botón corto (StatusBar, barra
   de paneles del visor). */

export interface PanelDef {
  titulo: string;
  rotulo: string;
  Componente: ComponentType;
}

export const PANELES = {
  tree: { titulo: "Árbol", rotulo: "Árbol", Componente: Tree },
  properties: { titulo: "Propiedades", rotulo: "Propiedades", Componente: Properties },
  chat: { titulo: "Asistente IA", rotulo: "Asistente IA", Componente: ChatPanel },
  history: { titulo: "Historial", rotulo: "Historial", Componente: HistoryPanel },
  reqs: { titulo: "Requisitos", rotulo: "Requisitos", Componente: RequirementsPanel },
  bom: { titulo: "BOM", rotulo: "BOM", Componente: BomPanel },
  checks: { titulo: "Validaciones", rotulo: "Validar", Componente: ChecksPanel },
  kin: { titulo: "Cinemática", rotulo: "Cinemática", Componente: KinematicsPanel },
  mates: { titulo: "Ensamblaje", rotulo: "Ensamblaje", Componente: MatesPanel },
  fisica: { titulo: "Física", rotulo: "Física", Componente: PhysicsPanel },
  ensamblaje: { titulo: "Montaje", rotulo: "Montaje", Componente: AssemblyPanel },
  boceto: { titulo: "Boceto de masas", rotulo: "Boceto", Componente: SketchBlockPanel },
} satisfies Record<string, PanelDef>;

export type PanelId = keyof typeof PANELES;

/** Paneles-herramienta (se conmutan desde la StatusBar y, en el visor, desde la barra de
   paneles), en el orden en que se muestran. Árbol, Propiedades y Asistente IA forman el
   layout por defecto de Completo y no se listan. */
export const HERRAMIENTAS: PanelId[] = [
  "history", "reqs", "bom", "checks", "kin", "mates", "fisica", "ensamblaje", "boceto",
];

export function esPanel(id: string): id is PanelId {
  return Object.prototype.hasOwnProperty.call(PANELES, id);
}
