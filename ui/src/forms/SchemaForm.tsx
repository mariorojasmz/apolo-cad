import { useEffect, useRef, useState } from "react";
import { useStore } from "../state/store";
import type { FeatureOut, JsonSchema } from "../types";
import Spinner from "../ui/Spinner";

/* Formulario generado automáticamente desde el JSON Schema (pydantic) de un
   comando. Los campos numéricos aceptan también expresiones paramétricas
   escritas como "=L/2" que se resuelven contra las variables del proyecto. */

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
};

const SELECTOR_MODES = [
  ["todas", "Todas"],
  ["direccion", "Por dirección"],
  ["cara", "Por cara"],
  ["longitud", "Por longitud"],
  ["cerca", "Cerca de un punto"],
] as const;
const SELECTOR_FACES = ["tope", "base", "min_x", "max_x", "min_y", "max_y"];

function SelectorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: SelectorValue;
  onChange: (v: SelectorValue) => void;
}) {
  const requestPick = useStore((s) => s.requestPick);
  const picking = useStore((s) => s.pickRequest !== null);
  const v = value ?? { mode: "todas" };

  const pick = () => {
    requestPick((point) => {
      onChange({ mode: "cerca", point: [...point], count: v.count ?? 1 });
    });
  };

  return (
    <div className="field selector-field">
      <label>{label}</label>
      <div className="selector-row">
        <select value={v.mode} onChange={(e) => onChange({ mode: e.target.value, count: v.count })}>
          {SELECTOR_MODES.map(([key, text]) => (
            <option key={key} value={key}>{text}</option>
          ))}
        </select>
        {v.mode === "direccion" && (
          <select value={v.direction ?? "z"} onChange={(e) => onChange({ ...v, direction: e.target.value })}>
            <option value="x">∥ X</option>
            <option value="y">∥ Y</option>
            <option value="z">∥ Z</option>
          </select>
        )}
        {v.mode === "cara" && (
          <select value={v.face ?? "tope"} onChange={(e) => onChange({ ...v, face: e.target.value })}>
            {SELECTOR_FACES.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
        )}
        {v.mode === "longitud" && (
          <>
            <input type="text" inputMode="decimal" placeholder="mín" style={{ width: 60 }}
              value={String(v.min ?? "")} onChange={(e) => onChange({ ...v, min: e.target.value })} />
            <input type="text" inputMode="decimal" placeholder="máx" style={{ width: 60 }}
              value={String(v.max ?? "")} onChange={(e) => onChange({ ...v, max: e.target.value })} />
          </>
        )}
        {v.mode === "cerca" && (
          <button type="button" className={picking ? "active" : ""} onClick={pick}>
            📍 {v.point ? `(${v.point.map((n) => Math.round(n)).join(", ")})` : "Elegir en viewport"}
          </button>
        )}
      </div>
      {v.mode === "cerca" && picking && <span className="hint">Haz clic sobre el sólido en el viewport…</span>}
    </div>
  );
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
  return out;
}

function resolveRef(field: JsonSchema, root: JsonSchema): JsonSchema {
  const ref = field.$ref ?? field.allOf?.[0]?.$ref;
  if (!ref) return field;
  const name = ref.split("/").pop()!;
  return root.$defs?.[name] ?? field;
}

function isVec3(field: JsonSchema, root: JsonSchema): boolean {
  const resolved = resolveRef(field, root);
  const props = resolved.properties;
  return !!props && VEC_KEYS.every((k) => k in props);
}

function isNumeric(field: JsonSchema): boolean {
  return field.type === "number" || field.type === "integer";
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

/** ¿Campo array de arrays (p. ej. nodes [x,y,z] / edges [i,j])? → textarea. */
function isMatrix(raw: JsonSchema, root: JsonSchema): boolean {
  const field = resolveRef(raw, root);
  if (field.type !== "array" || !field.items) return false;
  return resolveRef(field.items as JsonSchema, root).type === "array";
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

export function defaultValues(schema: JsonSchema): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, raw] of Object.entries(schema.properties ?? {})) {
    const field = resolveRef(raw, schema);
    if (raw.default !== undefined) out[key] = raw.default;
    else if (isVec3(raw, schema)) out[key] = { x: 0, y: 0, z: 0 };
    else if (field.enum) out[key] = field.enum[0];
    else if (field.type === "boolean") out[key] = false;
    else if (isNumeric(field)) out[key] = 0;
    else if (field.type === "array") out[key] = [];
    else out[key] = "";
  }
  return out;
}

function isSelector(raw: JsonSchema): boolean {
  return "x-selector" in (raw as Record<string, unknown>);
}

function normalize(schema: JsonSchema, values: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...values };
  for (const [key, raw] of Object.entries(schema.properties ?? {})) {
    const field = resolveRef(raw, schema);
    if (isSelector(raw)) {
      out[key] = normalizeSelector((out[key] as SelectorValue) ?? { mode: "todas" });
    } else if (isVec3(raw, schema)) {
      const vec = (out[key] as Record<string, unknown>) ?? {};
      out[key] = Object.fromEntries(VEC_KEYS.map((a) => [a, parseNumeric(vec[a] ?? 0)]));
    } else if (isMatrix(raw, schema)) {
      const cur = out[key];
      out[key] = typeof cur === "string" ? textToMatrix(cur) : cur;
    } else if (isNumeric(field)) {
      out[key] = parseNumeric(out[key]);
    }
  }
  return out;
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
      {Object.entries(schema.properties ?? {}).map(([key, raw]) => {
        const field = resolveRef(raw, schema);
        const label = raw.title ?? field.title ?? key;
        const unit = raw.description ?? "";

        if (isSelector(raw)) {
          return (
            <SelectorField
              key={key}
              label={label}
              value={(values[key] as SelectorValue) ?? { mode: "todas" }}
              onChange={(v) => setField(key, v)}
            />
          );
        }

        if (isVec3(raw, schema)) {
          const vec = (values[key] as Record<string, unknown>) ?? { x: 0, y: 0, z: 0 };
          return (
            <div className="field" key={key}>
              <label>{label}</label>
              <div className="vec3">
                {VEC_KEYS.map((axis) => (
                  <input
                    key={axis}
                    type="text"
                    inputMode="decimal"
                    value={String(vec[axis] ?? 0)}
                    title={`${axis.toUpperCase()} — número o =expresión`}
                    onChange={(e) => setField(key, { ...vec, [axis]: e.target.value })}
                  />
                ))}
              </div>
            </div>
          );
        }

        if (FEATURE_FIELDS.has(key) && features) {
          return (
            <div className="field" key={key}>
              <label>{label}</label>
              <select
                value={(values[key] as string) ?? ""}
                required={schema.required?.includes(key)}
                onChange={(e) => setField(key, e.target.value)}
              >
                <option value="">— elegir sólido —</option>
                {features.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name} ({f.id})
                  </option>
                ))}
              </select>
            </div>
          );
        }

        if (key === "tools" && field.type === "array" && features) {
          const selected = (values[key] as string[]) ?? [];
          return (
            <div className="field" key={key}>
              <label>{label}</label>
              <select
                multiple
                value={selected}
                onChange={(e) => setField(key, Array.from(e.target.selectedOptions).map((o) => o.value))}
              >
                {features.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name} ({f.id})
                  </option>
                ))}
              </select>
            </div>
          );
        }

        if (isMatrix(raw, schema)) {
          const text = typeof values[key] === "string" ? (values[key] as string) : matrixToText(values[key]);
          return (
            <div className="field" key={key}>
              <label>
                {label} {unit && <span className="unit">{unit}</span>}
              </label>
              <textarea
                rows={4}
                style={{ width: "100%", fontFamily: "monospace" }}
                placeholder="una fila por línea, valores por coma (acepta =expr)"
                value={text}
                onChange={(e) => setField(key, e.target.value)}
              />
            </div>
          );
        }

        if (field.enum) {
          return (
            <div className="field" key={key}>
              <label>{label}</label>
              <select value={String(values[key] ?? "")} onChange={(e) => setField(key, e.target.value)}>
                {field.enum.map((opt) => (
                  <option key={String(opt)} value={String(opt)}>
                    {String(opt)}
                  </option>
                ))}
              </select>
            </div>
          );
        }

        if (field.type === "boolean") {
          return (
            <div className="field field-inline" key={key}>
              <label>{label}</label>
              <input
                type="checkbox"
                checked={Boolean(values[key])}
                onChange={(e) => setField(key, e.target.checked)}
              />
            </div>
          );
        }

        if (isNumeric(field)) {
          return (
            <div className="field" key={key}>
              <label>
                {label} {unit && <span className="unit">{unit}</span>}
              </label>
              <input
                type="text"
                inputMode="decimal"
                placeholder="número o =expresión"
                title="Acepta un número o una expresión como =L/2"
                value={String(values[key] ?? "")}
                onChange={(e) => setField(key, e.target.value)}
              />
            </div>
          );
        }

        return (
          <div className="field" key={key}>
            <label>{label}</label>
            <input type="text" value={String(values[key] ?? "")} onChange={(e) => setField(key, e.target.value)} />
          </div>
        );
      })}
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
