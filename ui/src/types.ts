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

export interface CommandRecord {
  id: string;
  type: string;
  params: Record<string, unknown>;
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
  project_id: number | null;
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
