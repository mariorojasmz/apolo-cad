import {
  Activity, Anchor, Atom, Blocks, Boxes, CircuitBoard, ClipboardList, Cpu, Gauge, History, ListChecks, ListTree, Power,
  FlaskConical, ShieldCheck, SlidersHorizontal, Sparkles, Wind,
} from "lucide-react";

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
import PanelMandos from "../vivo/PanelMandos";
import PanelSenales from "../vivo/PanelSenales";
import PanelPlc from "../vivo/PanelPlc";
import PanelTablero from "../tablero/PanelTablero";
import PanelNeumatica from "../neumatica/PanelNeumatica";
import PanelPruebas from "../pruebas/PanelPruebas";
import { EXTENSIONES } from "../extensiones/registro";
import type { IdPanelExtension } from "../extensiones/tipos";
import { componerPaneles, type PanelDef } from "./componerPaneles";

export type { PanelDef } from "./componerPaneles";

/* Los paneles de Apolo, una sola vez: el mismo componente lo monta Dockview en Completo
   (`DockShell.tsx`) y un cajón en el visor (`visor/Cajon.tsx`, plan modo-visor D3). El
   viewport no está aquí: es el centro fijo del dock y nunca va en un cajón.
   `titulo` = cabecera (pestaña de Dockview, cajón); `rotulo` = botón corto (StatusBar, barra
   de paneles del visor); `icono` = el de los dos botones.
   A los del núcleo se suman los que registran las extensiones compiladas en el bundle
   (`extensiones/registro.ts`, plan núcleo-abierto-extensiones-privadas D5). */

const NUCLEO = {
  tree: { titulo: "Árbol", rotulo: "Árbol", Componente: Tree, icono: ListTree },
  properties: { titulo: "Propiedades", rotulo: "Propiedades", Componente: Properties, icono: SlidersHorizontal },
  chat: { titulo: "Asistente IA", rotulo: "Asistente IA", Componente: ChatPanel, icono: Sparkles },
  history: { titulo: "Historial", rotulo: "Historial", Componente: HistoryPanel, icono: History },
  reqs: { titulo: "Requisitos", rotulo: "Requisitos", Componente: RequirementsPanel, icono: ClipboardList },
  bom: { titulo: "BOM", rotulo: "BOM", Componente: BomPanel, icono: ListChecks },
  checks: { titulo: "Validaciones", rotulo: "Validar", Componente: ChecksPanel, icono: ShieldCheck },
  kin: { titulo: "Cinemática", rotulo: "Cinemática", Componente: KinematicsPanel, icono: Activity },
  mates: { titulo: "Ensamblaje", rotulo: "Ensamblaje", Componente: MatesPanel, icono: Boxes },
  fisica: { titulo: "Física", rotulo: "Física", Componente: PhysicsPanel, icono: Atom },
  ensamblaje: { titulo: "Montaje", rotulo: "Montaje", Componente: AssemblyPanel, icono: Anchor },
  boceto: { titulo: "Boceto de masas", rotulo: "Boceto", Componente: SketchBlockPanel, icono: Blocks },
  tablero: { titulo: "Tablero", rotulo: "Tablero", Componente: PanelTablero, icono: CircuitBoard },
  neumatica: { titulo: "Neumática", rotulo: "Neumática", Componente: PanelNeumatica, icono: Wind },
  pruebas: { titulo: "Pruebas", rotulo: "Pruebas", Componente: PanelPruebas, icono: FlaskConical },
  mandos: { titulo: "Mandos", rotulo: "Mandos", Componente: PanelMandos, icono: Power },
  senales: { titulo: "Señales", rotulo: "Señales", Componente: PanelSenales, icono: Gauge },
  plc: { titulo: "PLC", rotulo: "PLC", Componente: PanelPlc, icono: Cpu },
} satisfies Record<string, PanelDef>;

/** Un panel del núcleo: literal, así `tsc` rebota un id mal escrito («bmo»). */
export type PanelNucleo = keyof typeof NUCLEO;

/** Un panel del núcleo o de una extensión (`<nombre>.<panel>`, con punto: nunca pisa uno del
   núcleo). Lo que llega como texto suelto (layout guardado, cajón del visor) se valida con
   `esPanel` antes de indexar `PANELES`. */
export type PanelId = PanelNucleo | IdPanelExtension;

/** Paneles-herramienta del núcleo (se conmutan desde la StatusBar y, en el visor, desde la barra
   de paneles), en el orden en que se muestran. Árbol, Propiedades y Asistente IA (sólo con el
   chat prendido, `chat/activo.ts`) forman el layout por defecto de Completo y no se listan. */
const HERRAMIENTAS_NUCLEO: PanelNucleo[] = [
  "history", "reqs", "bom", "checks", "kin", "mates", "fisica", "ensamblaje", "boceto", "tablero", "neumatica", "pruebas", "mandos", "senales", "plc",
];

const COMPUESTO = componerPaneles(NUCLEO, HERRAMIENTAS_NUCLEO, EXTENSIONES);

export const PANELES: Readonly<Record<PanelId, PanelDef>> = COMPUESTO.paneles;

/** Las del núcleo y, detrás, las de las extensiones. */
export const HERRAMIENTAS: readonly PanelId[] = COMPUESTO.herramientas;

export function esPanel(id: string): id is PanelId {
  return Object.prototype.hasOwnProperty.call(PANELES, id);
}
