// Pure helpers for the schema-driven New run form and the runs table. The JSON Schemas come
// from `GET /api/cebra/schema` (built from the backend's Pydantic models).

export type Mode = "time" | "behaviour" | "hybrid";

export const MODES: { value: Mode; label: string; hint: string; prefix: string }[] = [
  {
    value: "time",
    label: "Time",
    hint: "Self-supervised. Uses time only, no behaviour labels.",
    prefix: "time",
  },
  {
    value: "behaviour",
    label: "Behaviour",
    hint: "Supervised by the behaviour labels you pick.",
    prefix: "beh",
  },
  {
    value: "hybrid",
    label: "Hybrid",
    hint: "Learns from both time and behaviour labels.",
    prefix: "hyb",
  },
];

export function modeLabel(mode: string): string {
  return MODES.find((m) => m.value === mode)?.label ?? mode;
}

/** The subset of JSON Schema that Pydantic emits for the param models. */
export type JsonSchema = {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  multipleOf?: number;
  enum?: unknown[];
  const?: unknown;
  readOnly?: boolean;
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  properties?: Record<string, JsonSchema>;
  /** `"labels"` puts a field in the form's Behaviour labels section. */
  "x-group"?: string;
};

export type FieldKind =
  | { kind: "integer" | "number"; min?: number; max?: number; step: number | "any" }
  | { kind: "enum"; options: string[] }
  | { kind: "multi-enum"; options: string[] }
  | { kind: "nullable-enum"; options: string[] }
  | { kind: "boolean"; locked: boolean };

function stringEnum(s: JsonSchema | undefined): string[] | null {
  if (!s?.enum || !s.enum.every((v) => typeof v === "string")) return null;
  return s.enum as string[];
}

/** Which input renders a property, or null when the schema shape is not supported. */
export function fieldKind(s: JsonSchema): FieldKind | null {
  if (s.type === "integer" || s.type === "number") {
    return {
      kind: s.type,
      min: s.minimum,
      max: s.maximum,
      step: s.multipleOf ?? (s.type === "integer" ? 1 : "any"),
    };
  }
  if (s.type === "string" && stringEnum(s)) return { kind: "enum", options: stringEnum(s)! };
  if (s.type === "array" && stringEnum(s.items)) {
    return { kind: "multi-enum", options: stringEnum(s.items)! };
  }
  if (s.anyOf?.length === 2 && s.anyOf.some((a) => a.type === "null")) {
    const options = stringEnum(s.anyOf.find((a) => a.type !== "null"));
    if (options) return { kind: "nullable-enum", options };
  }
  if (s.type === "boolean")
    return { kind: "boolean", locked: s.const !== undefined || !!s.readOnly };
  return null;
}

/** Form value for a property: numbers are kept as the text typed into the input. */
export type FieldValue = string | string[] | boolean | null;

export function initialValue(s: JsonSchema): FieldValue {
  const k = fieldKind(s);
  const d = s.const ?? s.default;
  switch (k?.kind) {
    case "integer":
    case "number":
      return typeof d === "number" ? String(d) : "";
    case "enum":
      return typeof d === "string" ? d : (k.options[0] ?? "");
    case "multi-enum":
      return Array.isArray(d) ? (d as string[]) : [];
    case "nullable-enum":
      return typeof d === "string" ? d : null;
    case "boolean":
      return d === true;
    default:
      return (d as FieldValue) ?? null;
  }
}

/** Client-side check of one value against its schema: an error message, or true. */
export function validateValue(s: JsonSchema, value: unknown): string | true {
  const k = fieldKind(s);
  if (k?.kind !== "integer" && k?.kind !== "number") return true;
  const text = typeof value === "string" ? value.trim() : String(value ?? "");
  if (text === "") return "Required";
  const n = Number(text);
  if (!Number.isFinite(n)) return "Enter a number";
  if (k.kind === "integer" && !Number.isInteger(n)) return "Enter a whole number";
  if (k.min !== undefined && n < k.min) return `Must be at least ${formatNumber(k.min)}`;
  if (k.max !== undefined && n > k.max) return `Must be at most ${formatNumber(k.max)}`;
  return true;
}

/** Form value -> request body value. */
export function toSubmitValue(s: JsonSchema, value: unknown): unknown {
  const k = fieldKind(s)?.kind;
  if (k === "integer" || k === "number") return Number(String(value).trim());
  return value;
}

/** Request body for one schema: every property, converted, in schema order. */
export function toSubmitObject(
  schema: JsonSchema,
  values: Record<string, unknown> | undefined,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(schema.properties ?? {}).map(([key, s]) => [
      key,
      toSubmitValue(s, values?.[key]),
    ]),
  );
}

/** `3e-4`, `0.5`, `512`: small numbers in exponent form, the way they are usually written. */
export function formatNumber(n: number): string {
  if (n !== 0 && Math.abs(n) < 1e-3) return n.toExponential();
  return String(n);
}

/** Table cell text for a stored param value. */
export function formatParam(value: unknown): string {
  if (value === null || value === undefined) return "None";
  if (typeof value === "number") return formatNumber(value);
  if (Array.isArray(value)) return value.length ? value.map(formatParam).join(", ") : "None";
  return String(value);
}

export type Column = { key: string; title: string };

/** Ordered union of the properties of several schemas (first appearance wins). */
export function schemaColumns(schemas: JsonSchema[]): Column[] {
  const seen = new Map<string, string>();
  for (const s of schemas) {
    for (const [key, prop] of Object.entries(s.properties ?? {})) {
      if (!seen.has(key)) seen.set(key, prop.title ?? key);
    }
  }
  return [...seen].map(([key, title]) => ({ key, title }));
}

/** `time-01`, `beh-03`: one more than the highest number used with the mode's prefix. */
export function nextRunName(mode: Mode, names: string[]): string {
  const prefix = MODES.find((m) => m.value === mode)!.prefix;
  const re = new RegExp(`^${prefix}-(\\d+)$`);
  let max = 0;
  for (const name of names) {
    const m = re.exec(name);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return `${prefix}-${String(max + 1).padStart(2, "0")}`;
}

function seconds(v: unknown): string {
  const n = Number(v);
  if (String(v ?? "").trim() === "" || !Number.isFinite(n)) return String(v ?? "?");
  return Number.isInteger(n) ? n.toFixed(1) : String(n);
}

/** `20 ms bins · stimOn_times −0.5 to +1.0 s · good units only` */
export function preprocessSummary(v: Record<string, unknown>): string {
  const parts = [
    `${String(v.bin_size_ms ?? "?").trim() || "?"} ms bins`,
    `${v.align_event} −${seconds(v.window_pre_s)} to +${seconds(v.window_post_s)} s`,
  ];
  if (v.good_units_only) parts.push("good units only");
  return parts.join(" · ");
}

/**
 * FastAPI error `loc` -> form field name: `["body","name"]` -> `name`,
 * `["body","params","output_dimension"]` -> `params.output_dimension` (deeper parts such as
 * an array index are dropped). Null when the error is not about one field.
 */
export function fieldFromLoc(loc: unknown): string | null {
  if (!Array.isArray(loc) || loc[0] !== "body") return null;
  const [, section, field] = loc;
  if (section === "name" || section === "mode") return section;
  if ((section === "params" || section === "preprocess") && typeof field === "string") {
    return `${section}.${field}`;
  }
  return null;
}

export type ApiErrorDetail = { loc?: unknown; msg?: string; type?: string };

/** The `detail` list of a FastAPI error body (422s, and this API's 409s). */
export function errorDetails(body: unknown): ApiErrorDetail[] {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (Array.isArray(detail)) return detail as ApiErrorDetail[];
  if (typeof detail === "string") return [{ msg: detail }];
  return [];
}
