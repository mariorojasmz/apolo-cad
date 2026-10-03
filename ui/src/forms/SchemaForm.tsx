import { useEffect, useRef, useState } from "react";
import { useStore } from "../state/store";
import type { FeatureOut, JsonSchema } from "../types";
import Spinner from "../ui/Spinner";
import Campo from "./Campo";

/* Formulario generado automáticamente desde el JSON Schema (pydantic) de un
   comando. Los campos numéricos aceptan también expresiones paramétricas
   escritas como "=L/2" que se resuelven contra las variables del proyecto.
   Los campos opcionales de pydantic (`X | None` → `anyOf: [X, {type:"null"}]`) se
   desenvuelven: se pinta el widget de X y el valor VACÍO se manda como null (= el
   default del backend). Los sub-modelos (Hélice, {u,v}…) se pintan anidados; si son
   opcionales, detrás de una casilla que los activa. El envoltorio de cada campo
   (rótulo, unidad, ⓘ y pista) es `Campo`. */

interface Props {
  schema: JsonSchema;
  initial?: Record<string, unknown>;
  features?: FeatureOut[];
  submitLabel: string;
  onSubmit: (values: Record<string, unknown>) => void;
  onChange?: (values: Record<string, unknown>) => void;
  onCancel?: () => void;
  busy?: boolean;
}

const VEC_KEYS = ["x", "y", "z"] as const;
const FEATURE_FIELDS = new Set(["feature", "target"]);

type SelectorValue = {
  mode: string;
  direction?: string;
  face?: string;
  min?: number | string;
  max?: number | string;
  point?: number[];
  count?: number;
  entidad?: string; // mates: cara | arista | ancla (sin widget propio, pero no se pierde al editar)
  name?: string; // modo "ancla": nombre del frame publicado por el componente
};

// Etiquetas de los modos del selector. La LISTA de modos sale del enum del schema
// (EdgeSelector.mode) para no desincronizarse del backend; un modo sin etiqueta se
// muestra por su clave. El fallback solo aplica si el schema no trae el enum.
const SELECTOR_MODE_LABELS: Record<string, string> = {
  todas: "Todas",
  direccion: "Por dirección",
  cara: "Por cara",
  longitud: "Por longitud",
  cerca: "Cerca de un punto",
  ancla: "Por ancla (nombre)",
};
const SELECTOR_MODES_FALLBACK = Object.keys(SELECTOR_MODE_LABELS);
const SELECTOR_FACES_FALLBACK = ["tope", "base", "min_x", "max_x", "min_y", "max_y"];

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/** ¿Valor «vacío» de un campo opcional? (→ se manda null = default del backend). */
function isBlank(v: unknown): boolean {
  return v === null || v === undefined || (typeof v === "string" && v.trim() === "");
}

/** Campo efectivo tras desenvolver `anyOf`. pydantic emite `X | None` como
 *  `anyOf: [X, {type: "null"}]` (X puede ser un `$ref`): se usa X con los metadatos del
 *  campo (title/description/default/x-selector) y `nullable` = vacío → null. Con más de
 *  una rama no nula (`multi`) no hay widget fiable → se edita como JSON. */
interface FieldInfo {
  eff: JsonSchema;
  nullable: boolean;
  multi: boolean;
}

function unwrap(raw: JsonSchema): FieldInfo {
  if (!raw.anyOf?.length) return { eff: raw, nullable: false, multi: false };
  const nonNull = raw.anyOf.filter((b) => b.type !== "null");
  const nullable = nonNull.length < raw.anyOf.length;
  if (nonNull.length !== 1) return { eff: raw, nullable, multi: true };
  const meta: JsonSchema = { ...raw };
  delete meta.anyOf;
  return { eff: { ...nonNull[0], ...meta }, nullable, multi: false };
}

function resolveRef(field: JsonSchema, root: JsonSchema): JsonSchema {
  const ref = field.$ref ?? field.allOf?.[0]?.$ref;
  if (!ref) return field;
  const name = ref.split("/").pop()!;
  return root.$defs?.[name] ?? field;
}

/** Opciones de un enum (desenvolviendo `X | None` y `$ref`); undefined si no hay. */
function enumOf(raw: JsonSchema | undefined, root: JsonSchema): string[] | undefined {
  if (!raw) return undefined;
  const opts = resolveRef(unwrap(raw).eff, root).enum;
  return opts?.length ? opts.map(String) : undefined;
}

function isVec3(field: JsonSchema, root: JsonSchema): boolean {
  const resolved = resolveRef(field, root);
  const props = resolved.properties;
  return !!props && VEC_KEYS.every((k) => k in props);
}

/** Sub-modelo con propiedades propias (HelixSpec, SlideUV, ChildFlap…): se pinta anidado. */
function isSubModel(field: JsonSchema, root: JsonSchema): boolean {
  const props = resolveRef(field, root).properties;
  return !!props && Object.keys(props).length > 0;
}

function isNumeric(field: JsonSchema): boolean {
  return field.type === "number" || field.type === "integer";
}

function isSelector(raw: JsonSchema): boolean {
  return "x-selector" in (raw as Record<string, unknown>);
}

/** "=expr" se conserva como string; cualquier otra cosa se intenta como número. */
function parseNumeric(raw: unknown): unknown {
  if (typeof raw !== "string") return raw;
  const t = raw.trim();
  if (t === "") return 0;
  if (t.startsWith("=")) return t;
  const n = Number(t);
  return Number.isNaN(n) ? t : n;
}

/** ¿Campo array de arrays de ESCALARES (p. ej. nodes [x,y,z] / edges [i,j])? → textarea.
 *  Un array de arrays de sub-modelos (huecos de una superficie) NO cabe en «valores por coma». */
function isMatrix(raw: JsonSchema, root: JsonSchema): boolean {
  const field = resolveRef(raw, root);
  if (field.type !== "array" || !field.items) return false;
  const row = resolveRef(field.items, root);
  if (row.type !== "array") return false;
  const cell = row.items ? resolveRef(row.items, root) : undefined;
  return !cell || (cell.type !== "object" && !cell.properties);
}

function matrixToText(v: unknown): string {
  if (!Array.isArray(v)) return typeof v === "string" ? v : "";
  return v.map((row) => (Array.isArray(row) ? row.join(", ") : String(row))).join("\n");
}

function textToMatrix(s: string): unknown[][] {
  return s
    .split(/\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(",").map((t) => parseNumeric(t.trim())));
}

/** Valor sin widget fiable (anyOf de varias ramas, lista opcional de sub-modelos) → JSON en texto. */
function jsonText(v: unknown): string {
  if (typeof v === "string") return v;
  return v === null || v === undefined ? "" : JSON.stringify(v);
}

/** Parsea el JSON al enviar; si no es JSON válido se manda tal cual (el backend lo rechaza
 *  con un error claro — no se inventa un valor). */
function parseJsonLoose(value: unknown, nullable: boolean): unknown {
  if (typeof value !== "string") return value;
  const t = value.trim();
  if (t === "") return nullable ? null : value;
  try {
    return JSON.parse(t);
  } catch {
    return value;
  }
}

/** Valor por defecto de UN campo (el del schema si lo trae; un opcional sin default → null). */
function defaultFor(raw: JsonSchema, root: JsonSchema): unknown {
  const { eff, nullable, multi } = unwrap(raw);
  if (eff.default !== undefined) return eff.default;
  if (nullable || multi) return null;
  return objectOrScalarDefault(eff, root);
}

/** Default «activo» (ignora la opcionalidad): lo que se pone al ACTIVAR un sub-modelo opcional. */
function objectOrScalarDefault(eff: JsonSchema, root: JsonSchema): unknown {
  const field = resolveRef(eff, root);
  if (isSelector(eff)) return { mode: "todas" };
  if (isVec3(eff, root)) return { x: 0, y: 0, z: 0 };
  if (isSubModel(eff, root)) return defaultValues(field, root);
  if (field.enum) return field.enum[0];
  if (field.type === "boolean") return false;
  if (isNumeric(field)) return 0;
  if (field.type === "array") return [];
  return "";
}

export function defaultValues(schema: JsonSchema, root: JsonSchema = schema): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, raw] of Object.entries(schema.properties ?? {})) {
    out[key] = defaultFor(raw, root);
  }
  return out;
}

function normalizeSelector(v: SelectorValue): SelectorValue {
  const out: SelectorValue = { mode: v.mode };
  if (v.mode === "direccion") out.direction = v.direction ?? "z";
  if (v.mode === "cara") out.face = v.face ?? "tope";
  if (v.mode === "longitud") {
    if (v.min !== undefined && String(v.min).trim() !== "") out.min = Number(v.min);
    if (v.max !== undefined && String(v.max).trim() !== "") out.max = Number(v.max);
  }
  if (v.mode === "cerca") {
    out.point = v.point;
    out.count = v.count ?? 1;
  }
  if (v.mode === "ancla") out.name = (v.name ?? "").trim();
  if (v.entidad) out.entidad = v.entidad;
  return out;
}

/** Valor de UN campo listo para la API (recursivo en sub-modelos). */
function normalizeValue(raw: JsonSchema, root: JsonSchema, value: unknown): unknown {
  const { eff, nullable, multi } = unwrap(raw);
  if (multi) return parseJsonLoose(value, nullable);
  if (nullable && isBlank(value)) return null; // opcional vacío → null (default del backend)
  const field = resolveRef(eff, root);
  if (isSelector(eff)) {
    return normalizeSelector(isObj(value) ? (value as SelectorValue) : { mode: "todas" });
  }
  if (isVec3(eff, root)) {
    const vec: Record<string, unknown> = isObj(value) ? value : {};
    return Object.fromEntries(VEC_KEYS.map((a) => [a, parseNumeric(vec[a] ?? 0)]));
  }
  if (isSubModel(eff, root)) {
    return isObj(value) ? normalizeObject(field, root, value) : value;
  }
  if (isMatrix(eff, root)) {
    return typeof value === "string" ? textToMatrix(value) : value;
  }
  if (nullable && field.type === "array") return parseJsonLoose(value, nullable);
  if (isNumeric(field)) return parseNumeric(value);
  return value;
}

function normalizeObject(schema: JsonSchema, root: JsonSchema, values: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...values };
  for (const [key, raw] of Object.entries(schema.properties ?? {})) {
    out[key] = normalizeValue(raw, root, out[key]);
  }
  return out;
}

function normalize(schema: JsonSchema, values: Record<string, unknown>): Record<string, unknown> {
  return normalizeObject(schema, schema, values);
}

function SelectorField({
  label,
  campo,
  selector,
  root,
  nullable,
  value,
  onChange,
}: {
  label: string;
  campo: JsonSchema; // metadatos del campo (ⓘ, pista)
  selector: JsonSchema; // EdgeSelector resuelto: de aquí salen los enums de modo/cara
  root: JsonSchema;
  nullable: boolean;
  value: SelectorValue | null;
  onChange: (v: SelectorValue | null) => void;
}) {
  const requestPick = useStore((s) => s.requestPick);
  const picking = useStore((s) => s.pickRequest !== null);
  const modes = enumOf(selector.properties?.mode, root) ?? SELECTOR_MODES_FALLBACK;
  const faces = enumOf(selector.properties?.face, root) ?? SELECTOR_FACES_FALLBACK;
  const v = value;

  const pick = () => {
    requestPick((point) => {
      onChange({ mode: "cerca", point: [...point], count: v?.count ?? 1, entidad: v?.entidad });
    });
  };

  return (
    <Campo rotulo={label} campo={campo} className="selector-field">
      <div className="selector-row">
        <select
          value={v?.mode ?? ""}
          onChange={(e) =>
            onChange(e.target.value === "" ? null : { mode: e.target.value, count: v?.count, entidad: v?.entidad })
          }
        >
          {nullable && <option value="">— ninguna —</option>}
          {modes.map((key) => (
            <option key={key} value={key}>{SELECTOR_MODE_LABELS[key] ?? key}</option>
          ))}
        </select>
        {v?.mode === "direccion" && (
          <select value={v.direction ?? "z"} onChange={(e) => onChange({ ...v, direction: e.target.value })}>
            <option value="x">∥ X</option>
            <option value="y">∥ Y</option>
            <option value="z">∥ Z</option>
          </select>
        )}
        {v?.mode === "cara" && (
          <select value={v.face ?? "tope"} onChange={(e) => onChange({ ...v, face: e.target.value })}>
            {faces.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
        )}
        {v?.mode === "longitud" && (
          <>
            <input type="text" inputMode="decimal" placeholder="mín" style={{ width: 60 }}
              value={String(v.min ?? "")} onChange={(e) => onChange({ ...v, min: e.target.value })} />
            <input type="text" inputMode="decimal" placeholder="máx" style={{ width: 60 }}
              value={String(v.max ?? "")} onChange={(e) => onChange({ ...v, max: e.target.value })} />
          </>
        )}
        {v?.mode === "cerca" && (
          <button type="button" className={picking ? "active" : ""} onClick={pick}>
            📍 {v.point ? `(${v.point.map((n) => Math.round(n)).join(", ")})` : "Elegir en viewport"}
          </button>
        )}
        {v?.mode === "ancla" && (
          <input type="text" placeholder="nombre del ancla" style={{ width: 120 }}
            value={v.name ?? ""} onChange={(e) => onChange({ ...v, name: e.target.value })} />
        )}
      </div>
      {v?.mode === "cerca" && picking && <span className="hint">Haz clic sobre la pieza en el viewport…</span>}
    </Campo>
  );
}

interface FieldProps {
  name: string;
  raw: JsonSchema; // schema del campo tal cual (puede traer anyOf)
  root: JsonSchema; // schema raíz del comando (dueño de los $defs)
  value: unknown;
  onChange: (v: unknown) => void;
  features?: FeatureOut[];
  required?: boolean;
}

/** Un campo del formulario; recursivo para los sub-modelos. */
function FieldView({ name, raw, root, value, onChange, features, required }: FieldProps) {
  const { eff, nullable, multi } = unwrap(raw);
  const field = resolveRef(eff, root);
  const label = eff.title ?? field.title ?? name;
  const meta = { rotulo: label, campo: eff };

  if (multi) {
    return (
      <Campo {...meta} unidad="JSON">
        <textarea
          rows={2}
          style={{ width: "100%", fontFamily: "monospace" }}
          placeholder={nullable ? "vacío = sin valor · valor en JSON" : "valor en JSON"}
          value={jsonText(value)}
          onChange={(e) => onChange(e.target.value)}
        />
      </Campo>
    );
  }

  if (isSelector(eff)) {
    return (
      <SelectorField
        label={label}
        campo={eff}
        selector={field}
        root={root}
        nullable={nullable}
        value={isObj(value) ? (value as SelectorValue) : nullable ? null : { mode: "todas" }}
        onChange={onChange}
      />
    );
  }

  if (isVec3(eff, root) || isSubModel(eff, root)) {
    // Opcional → casilla que lo activa (valor por defecto) o lo anula (null).
    const on = !nullable || isObj(value);
    const vec3 = isVec3(eff, root);
    const obj: Record<string, unknown> = vec3
      ? (isObj(value) ? value : { x: 0, y: 0, z: 0 })
      : { ...defaultValues(field, root), ...(isObj(value) ? value : {}) };
    const casilla = nullable && (
      <input
        type="checkbox"
        checked={on}
        title="Activar / dejar sin valor"
        onChange={(e) => onChange(e.target.checked ? objectOrScalarDefault(eff, root) : null)}
      />
    );
    return (
      <Campo {...meta} enCabeza={casilla}>
        {on && vec3 && (
          <div className="vec3">
            {VEC_KEYS.map((axis) => (
              <input
                key={axis}
                type="text"
                inputMode="decimal"
                value={String(obj[axis] ?? 0)}
                title={`${axis.toUpperCase()} — número o =expresión`}
                onChange={(e) => onChange({ ...obj, [axis]: e.target.value })}
              />
            ))}
          </div>
        )}
        {on && !vec3 && (
          <div className="sub-form">
            {Object.entries(field.properties ?? {}).map(([k, r]) => (
              <FieldView
                key={k}
                name={k}
                raw={r}
                root={root}
                value={obj[k]}
                onChange={(v) => onChange({ ...obj, [k]: v })}
                required={field.required?.includes(k)}
              />
            ))}
          </div>
        )}
      </Campo>
    );
  }

  if (FEATURE_FIELDS.has(name) && features) {
    return (
      <Campo {...meta}>
        <select value={(value as string) ?? ""} required={required} onChange={(e) => onChange(e.target.value)}>
          <option value="">— elegir pieza —</option>
          {features.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name} ({f.id})
            </option>
          ))}
        </select>
      </Campo>
    );
  }

  if (name === "tools" && field.type === "array" && features) {
    const selected = (value as string[]) ?? [];
    return (
      <Campo {...meta}>
        <select
          multiple
          value={selected}
          onChange={(e) => onChange(Array.from(e.target.selectedOptions).map((o) => o.value))}
        >
          {features.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name} ({f.id})
            </option>
          ))}
        </select>
      </Campo>
    );
  }

  if (isMatrix(eff, root)) {
    const text = typeof value === "string" ? value : matrixToText(value);
    return (
      <Campo {...meta}>
        <textarea
          rows={4}
          style={{ width: "100%", fontFamily: "monospace" }}
          placeholder={`una fila por línea, valores por coma (acepta =expr)${nullable ? " · vacío = sin valor" : ""}`}
          value={text}
          onChange={(e) => onChange(e.target.value)}
        />
      </Campo>
    );
  }

  if (nullable && field.type === "array") {
    return (
      <Campo {...meta}>
        <textarea
          rows={2}
          style={{ width: "100%", fontFamily: "monospace" }}
          placeholder="vacío = sin valor · lista en JSON, p. ej. [2, 3]"
          value={jsonText(value)}
          onChange={(e) => onChange(e.target.value)}
        />
      </Campo>
    );
  }

  if (field.enum) {
    return (
      <Campo {...meta}>
        <select
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) => onChange(nullable && e.target.value === "" ? null : e.target.value)}
        >
          {nullable && <option value="">— ninguno —</option>}
          {field.enum.map((opt) => (
            <option key={String(opt)} value={String(opt)}>
              {String(opt)}
            </option>
          ))}
        </select>
      </Campo>
    );
  }

  if (field.type === "boolean") {
    const casilla = <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />;
    return <Campo {...meta} enCabeza={casilla} />;
  }

  if (isNumeric(field)) {
    return (
      <Campo {...meta}>
        <input
          type="text"
          inputMode="decimal"
          placeholder={nullable ? "vacío = automático · número o =expresión" : "número o =expresión"}
          title="Acepta un número o una expresión como =L/2"
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        />
      </Campo>
    );
  }

  return (
    <Campo {...meta}>
      <input
        type="text"
        placeholder={nullable ? "(opcional)" : undefined}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    </Campo>
  );
}

export default function SchemaForm({ schema, initial, features, submitLabel, onSubmit, onChange, onCancel, busy }: Props) {
  const [values, setValues] = useState<Record<string, unknown>>({});
  const changeRef = useRef(onChange);
  changeRef.current = onChange;

  useEffect(() => {
    setValues({ ...defaultValues(schema), ...(initial ?? {}) });
  }, [schema, initial]);

  const setField = (key: string, value: unknown) => {
    setValues((v) => {
      const next = { ...v, [key]: value };
      changeRef.current?.(normalize(schema, next));
      return next;
    });
  };

  return (
    <form
      className="schema-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(normalize(schema, values));
      }}
    >
      {Object.entries(schema.properties ?? {}).map(([key, raw]) => (
        <FieldView
          key={key}
          name={key}
          raw={raw}
          root={schema}
          value={values[key]}
          onChange={(v) => setField(key, v)}
          features={features}
          required={schema.required?.includes(key)}
        />
      ))}
      <div className="form-actions">
        {onCancel && (
          <button type="button" className="ghost" onClick={onCancel} disabled={busy}>
            Cancelar
          </button>
        )}
        <button type="submit" className="primary btn-busy" disabled={busy}>
          {busy && <Spinner size={13} />}
          {busy ? "Procesando…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
