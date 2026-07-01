/* Iconografía (lucide-react). Centraliza el mapeo comando→icono para que la toolbar
   ribbon siga siendo schema-driven: un comando nuevo del backend cae en su pestaña con
   el icono FALLBACK si no se mapea aquí. Importar SIEMPRE por icono (tree-shaking). */
import {
  Box, Cylinder, Pentagon, RotateCcw, Columns3, FileInput, ScrollText,
  PenTool, Disc, Waypoints, Spline,
  Combine, Scissors, Drill, FlipHorizontal2, Rows3, CircleDot, Move3d, Magnet, Trash2,
  Link2, Bot, Cog,
  History, ListChecks, ShieldCheck, Activity, Boxes, Atom, Anchor, ClipboardList,
  type LucideIcon,
} from "lucide-react";

export const COMMAND_ICONS: Record<string, LucideIcon> = {
  // crear
  create_box: Box,
  create_cylinder: Cylinder,
  create_extrude_poly: Pentagon,
  create_revolve: RotateCcw,
  create_structural_profile: Columns3,
  import_step: FileInput,
  run_script: ScrollText,
  // croquis
  sketch_extrude: PenTool,
  sketch_revolve: Disc,
  sketch_loft: Waypoints,
  sketch_sweep: Spline,
  // modificar
  boolean_op: Combine,
  fillet: CircleDot,
  chamfer: Scissors,
  shell: Box,
  drill_hole: Drill,
  mirror_feature: FlipHorizontal2,
  pattern_linear: Rows3,
  pattern_circular: RotateCcw,
  transform: Move3d,
  attach: Magnet,
  delete_feature: Trash2,
  // ensamblaje / robótica
  add_mate: Link2,
  add_joint: Cog,
  create_robot_arm: Bot,
  // biblioteca
  create_frame: Columns3,
  create_weldment: Combine,
  create_conveyor: Boxes,
  create_sheet_metal: Pentagon,
  insert_component: Boxes,
};

const FALLBACK: LucideIcon = Box;

export function iconFor(type: string): LucideIcon {
  return COMMAND_ICONS[type] ?? FALLBACK;
}

/** Iconos de los paneles inferiores (status bar + cabecera del dock). */
export const PANEL_ICONS: Record<string, LucideIcon> = {
  history: History,
  reqs: ClipboardList,
  bom: ListChecks,
  checks: ShieldCheck,
  kin: Activity,
  mates: Boxes,
  fisica: Atom,
  ensamblaje: Anchor,
};
