export interface Mesh {
  positions: number[];
  indices: number[];
}

export interface FeatureOut {
  id: string;
  name: string;
  visible: boolean;
  color: string;
  volume_mm3: number;
  bbox: { min: number[]; max: number[] };
  mesh: Mesh | null;
  mesh_key: string | null;
  matrix: number[] | null;
  command_id: string;
  command_type: string | null;
  component: string | null;
  cut_length: number | null;
  group: string | null;
  is_guide?: boolean;  // boceto-guía (blockout): geometría de intención, fuera de BOM/masa/interferencia
  rev?: number;  // revisión de GEOMETRÍA (V6.2b): sube al cambiar el shape; estable si no
  same?: boolean;  // delta: el cliente ya tiene esta geometría (se mergea la anterior)
}

export interface CatalogItem {
  ref: string;
  name: string;
  category: string;
  description: string;
  specs: Record<string, string | number>;
  weight: number;
  cuttable: boolean;
  default_length: number | null;
}

export interface BomRow {
  ref: string;
  descripcion: string;
  categoria: string;
  cantidad: number;
  longitud_mm: number | null;
  peso_unitario_kg: number | null;
  peso_total_kg: number | null;
}

/* Requisitos del proyecto (bases de diseño): claves numéricas de convención +
   texto libre. Todas opcionales; el backend valida las numéricas. */
export interface Requirements {
  carga_kg?: number;
  largo_paquete_mm?: number;
  ancho_paquete_mm?: number;
  alto_paquete_mm?: number;
  velocidad_m_s?: number;
  inclinacion_deg?: number;
  temperatura_c?: number;
  tipo_cambio?: number;
  producto?: string;
  entorno?: string;
  normativa?: string;
  notas?: string;
  moneda?: string;
  [key: string]: number | string | boolean | undefined;
}

/* BOM costeado (/api/costing.json): filas del BOM + costo con su fuente. */
export interface CostRow extends BomRow {
  costo_ud_usd: number | null;
  costo_total_usd: number | null;
  costo_fuente: string;
}

export interface CostTotals {
  catalogo_usd: number;
  fabricacion_usd: number;
  total_usd: number;
  por_categoria: Record<string, number>;
  n_filas_sin_costo: number;
  item_mas_costoso: { ref: string; descripcion: string; costo_total_usd: number } | null;
}

export interface CostingOut {
  rows: CostRow[];
  totales: CostTotals;
}

export interface CommandRecord {
  id: string;
  type: string;
  params: Record<string, unknown>;
}

/* Sub-ensamblaje declarado (V5.2): grupo con nombre por command_ids, anidable. */
export interface GroupOut {
  name: string;
  parent: string | null;
  role: string | null;
  members: string[];
  command_id: string;
  missing_members: string[];
}

export interface VariableOut {
  name: string;
  expression: string;
  value: number | null;
  command_id: string;
}

export interface DocumentOut {
  name: string;
  commands: CommandRecord[];
  can_undo: boolean;
  can_redo: boolean;
  variables: VariableOut[];
  configurations: string[];
  configuration_values?: Record<string, Record<string, string>>;  // V6.4c: {variante: {var: expr}}
  groups: GroupOut[];
  project_id: number | null;
  // robustez (V6.1): comandos suprimidos por una carga tolerante + estado del autosave
  suppressed_commands?: { command_id: string | null; type: string; error: string }[];
  autosave_failed?: string | null;
}

export interface ProjectInfo {
  id: number;
  name: string;
  updated_at: string;
  pieces: number;
}

export interface RevisionInfo {
  id: number;
  note: string;
  created_at: string;
  pieces: number;
}

export interface SceneOut {
  features: FeatureOut[];
  definitions: Record<string, Mesh>;
  document: DocumentOut;
  epoch?: string;  // epoch de proceso (V6.2e): invalida los revs del cliente tras un restart
}

export interface CommandSchema {
  type: string;
  title: string;
  category: string;
  kind: string;
  description: string;
  schema: JsonSchema;
}

export interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  enum?: (string | number)[];
  const?: string | number;
  default?: unknown;
  items?: JsonSchema;
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  allOf?: JsonSchema[];
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  minimum?: number;
  maximum?: number;
}

export interface ChatAction {
  type: string;
  params: Record<string, unknown>;
  reason: string;
}

export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  actions?: ChatAction[];
  actionsStatus?: "pending" | "accepted" | "rejected" | "error";
  error?: string;
  tools?: string[];
}

export interface CheckResult {
  regla: string;
  estado: "ok" | "aviso" | "error";
  detalle: string;
  recomendacion?: string;
}

export interface InterferenceOut {
  solidos: number;
  parejas_analizadas: number;
  truncado: boolean;
  interferencias: { a: string; nombre_a: string; b: string; nombre_b: string; volumen_mm3: number }[];
  avisos_pose?: string[];
}

export interface ChecksOut {
  interferencias: InterferenceOut;
  ingenieria: CheckResult[] | null;
}

export interface JointOut {
  name: string;
  type: "fija" | "giratoria" | "continua" | "prismatica";
  parent: string;
  child: string;
  origin: number[];
  axis: number[];
  lower: number;
  upper: number;
  command_id: string;
}

export interface KinematicsOut {
  joints: JointOut[];
  roots: string[];
  errors: string[];
}

export interface RailConstraint {
  name: string;
  joint: string; // junta dependiente (se resuelve, no se arrastra)
  anchor: number[];
  point: number[];
  axis: number[];
  command_id: string;
}

export interface MotionKeyframe {
  t: number;
  values: Record<string, number>;
}

export interface MotionStudy {
  name: string;
  keyframes: MotionKeyframe[];
  duration: number;
}

export interface MotionOut {
  studies: MotionStudy[];
}

export interface MateRow {
  name: string;
  type: string;
  feature_a: string;
  feature_b: string;
  value: number;
  flip: boolean;
  command_id: string;
}

// ---- Física (drop-test): el backend devuelve la trayectoria completa ----
export interface PhysicsProduct {
  name: string;
  w: number;
  d: number;
  h: number;
  x: number;
  y: number;
  z: number;
  mass: number;
}

/** Un fotograma: tiempo (s) + pose 4×4 FILA-MAYOR (mm) por producto. */
export interface DropFrame {
  t: number;
  poses: Record<string, number[][]>;
}

export interface DropResult {
  frames: DropFrame[];
  resting: Record<string, number[]>;
  settled: boolean;
  products: PhysicsProduct[];
}

/** Caja de entrada para soltar (mass/x/y/z opcionales → el backend rellena). */
export interface DropProductIn {
  w: number;
  d: number;
  h: number;
  x?: number;
  y?: number;
  z?: number;
  mass?: number;
}

export interface DropRequest {
  products: DropProductIn[];
  seconds?: number;
  gravity?: number;
  fps?: number;
}

// ---- Validación de ensamblaje (conectividad + gravedad) ----
export interface SoundnessOut {
  has_ground: boolean;
  n_total: number;
  n_grounded: number;
  n_floating: number;
  floating: string[];
  isolated: string[];
  floating_detail: { id: string; nombre: string }[];
  autodetect?: { floor_z: number; n_grounds: number; n_contactos: number };
}

export interface StabilityOut {
  n_grounded: number;
  n_dynamic: number;
  fell: { id: string; nombre: string; caida_mm: number }[];
  estables: { id: string; nombre: string }[];
  settled: boolean;
  mensaje?: string;
}

// Reporte de grados de libertad del ensamblaje (V6.3c, conteo Grübler).
export interface DofFeature {
  id: string;
  name: string;
  dof: number;
  estado: "fijo" | "parcial" | "libre" | "sobre_restringido";
  restringido_por: string[];
}

export interface DofOut {
  features: DofFeature[];
  total_dof: number;
  libres: number;
  sobre_restringidos: number;
  resumen: string;
  nota: string;
}

export interface StabilityRequest {
  with_autodetect?: boolean;
  exclude?: string[];
  seconds?: number;
  gravity?: number;
  fps?: number;
  include_frames?: boolean;  // pide las poses por fotograma para animar en el viewport
}

// Uniones de ensamblaje declaradas (conectividad persistida en el modelo).
export interface FastenerRow {
  name: string;
  a: string;
  b: string;
  kind: string;  // perno | soldadura | pegado | contacto
  nota: string;
  command_id: string;
}

export interface GroundRow {
  name: string;
  feature: string;
  nota: string;
  command_id: string;
}

export interface ConnectivityOut {
  fasteners: FastenerRow[];
  grounds: GroundRow[];
}

// Pieza dinámica de la sim de gravedad (se anima su MALLA REAL, por eso lleva `com`).
export interface GravityProduct {
  name: string;   // clave MuJoCo (_safe_name) en frames.poses
  id: string;     // feature id → malla en ctx.meshes
  nombre: string;
  w: number;
  d: number;
  h: number;
  com: number[];  // [x,y,z] mm: centro del cuerpo (necesario para componer la pose con baseMatrix)
}

// StabilityOut + frames + products tipados, cuando se pide include_frames (para el viewport).
export interface GravityResult {
  n_grounded: number;
  n_dynamic: number;
  fell: { id: string; nombre: string; caida_mm: number }[];
  estables: { id: string; nombre: string }[];
  settled: boolean;
  mensaje?: string;
  products: GravityProduct[];
  frames: DropFrame[];
}
