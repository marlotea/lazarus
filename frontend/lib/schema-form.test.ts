import { describe, expect, it } from "vitest";
import {
  errorDetails,
  fieldFromLoc,
  fieldKind,
  formatParam,
  initialValue,
  nextRunName,
  preprocessSummary,
  schemaColumns,
  toSubmitObject,
  validateValue,
  type JsonSchema,
} from "@/lib/schema-form";

const int: JsonSchema = {
  type: "integer",
  title: "Batch size",
  minimum: 64,
  maximum: 4096,
  default: 512,
};
const float: JsonSchema = {
  type: "number",
  title: "Learning rate",
  minimum: 1e-6,
  maximum: 0.1,
  default: 3e-4,
};

describe("fieldKind / initialValue", () => {
  it("maps each supported shape", () => {
    expect(fieldKind(int)).toEqual({ kind: "integer", min: 64, max: 4096, step: 1 });
    expect(fieldKind(float)).toMatchObject({ kind: "number", step: "any" });
    expect(fieldKind({ type: "string", enum: ["a", "b"] })).toEqual({
      kind: "enum",
      options: ["a", "b"],
    });
    expect(fieldKind({ type: "array", items: { type: "string", enum: ["x"] } })?.kind).toBe(
      "multi-enum",
    );
    expect(fieldKind({ anyOf: [{ type: "string", enum: ["x"] }, { type: "null" }] })?.kind).toBe(
      "nullable-enum",
    );
    expect(fieldKind({ type: "boolean", const: true })).toEqual({ kind: "boolean", locked: true });
    expect(fieldKind({ type: "object" })).toBeNull();
    expect(fieldKind({ type: "string" })).toBeNull();
  });

  it("starts from the default, numbers as text", () => {
    expect(initialValue(int)).toBe("512");
    expect(initialValue(float)).toBe("0.0003");
    expect(
      initialValue({ anyOf: [{ type: "string", enum: ["x"] }, { type: "null" }], default: null }),
    ).toBeNull();
  });
});

describe("validateValue", () => {
  it("checks numbers against the schema", () => {
    expect(validateValue(int, "512")).toBe(true);
    expect(validateValue(int, "")).toBe("Required");
    expect(validateValue(int, "abc")).toBe("Enter a number");
    expect(validateValue(int, "100.5")).toBe("Enter a whole number");
    expect(validateValue(int, "10")).toBe("Must be at least 64");
    expect(validateValue(int, "5000")).toBe("Must be at most 4096");
    expect(validateValue(float, "1e-7")).toBe("Must be at least 1e-6");
    expect(validateValue(float, "0.001")).toBe(true);
    expect(validateValue({ type: "string", enum: ["a"] }, "z")).toBe(true);
  });
});

describe("toSubmitObject", () => {
  it("converts every schema property in order", () => {
    const schema: JsonSchema = {
      properties: {
        batch_size: int,
        learning_rate: float,
        distance: { type: "string", enum: ["cosine"] },
      },
    };
    const body = toSubmitObject(schema, {
      learning_rate: "0.001",
      batch_size: " 256 ",
      distance: "cosine",
      extra: 1,
    });
    expect(body).toEqual({ batch_size: 256, learning_rate: 0.001, distance: "cosine" });
    expect(Object.keys(body)).toEqual(["batch_size", "learning_rate", "distance"]);
  });
});

describe("formatParam", () => {
  it("formats stored values for the table", () => {
    expect(formatParam(3e-4)).toBe("3e-4");
    expect(formatParam(1e-6)).toBe("1e-6");
    expect(formatParam(1)).toBe("1");
    expect(formatParam(0.5)).toBe("0.5");
    expect(formatParam(["wheel_velocity", "signed_contrast"])).toBe(
      "wheel_velocity, signed_contrast",
    );
    expect(formatParam(null)).toBe("None");
    expect(formatParam(true)).toBe("true");
  });
});

describe("schemaColumns", () => {
  it("unions properties in first-seen order with titles", () => {
    const a: JsonSchema = { properties: { x: { title: "X" }, y: { title: "Y" } } };
    const b: JsonSchema = { properties: { x: { title: "X2" }, z: {} } };
    expect(schemaColumns([a, b])).toEqual([
      { key: "x", title: "X" },
      { key: "y", title: "Y" },
      { key: "z", title: "z" },
    ]);
  });
});

describe("nextRunName", () => {
  it("takes one more than the highest number of the mode's prefix", () => {
    expect(nextRunName("time", [])).toBe("time-01");
    expect(nextRunName("behaviour", ["beh-01", "beh-03", "time-07", "beh-x"])).toBe("beh-04");
    expect(nextRunName("hybrid", ["hyb-09"])).toBe("hyb-10");
    expect(nextRunName("time", ["time-1"])).toBe("time-02");
  });
});

describe("preprocessSummary", () => {
  it("describes the preprocessing in one line", () => {
    const v = {
      bin_size_ms: "20",
      align_event: "stimOn_times",
      window_pre_s: "0.5",
      window_post_s: "1",
      good_units_only: true,
    };
    expect(preprocessSummary(v)).toBe("20 ms bins · stimOn_times −0.5 to +1.0 s · good units only");
    expect(preprocessSummary({ ...v, window_pre_s: "0.25", good_units_only: false })).toBe(
      "20 ms bins · stimOn_times −0.25 to +1.0 s",
    );
  });
});

describe("fieldFromLoc / errorDetails", () => {
  it("maps FastAPI error locations onto form fields", () => {
    expect(fieldFromLoc(["body", "name"])).toBe("name");
    expect(fieldFromLoc(["body", "params", "output_dimension"])).toBe("params.output_dimension");
    expect(fieldFromLoc(["body", "params", "continuous_labels", 0])).toBe(
      "params.continuous_labels",
    );
    expect(fieldFromLoc(["body", "preprocess", "bin_size_ms"])).toBe("preprocess.bin_size_ms");
    expect(fieldFromLoc(["body"])).toBeNull();
    expect(fieldFromLoc(["body", "params"])).toBeNull();
    expect(fieldFromLoc(["path", "experiment_id"])).toBeNull();
  });

  it("reads the detail list", () => {
    expect(errorDetails({ detail: [{ loc: ["body"], msg: "m" }] })).toEqual([
      { loc: ["body"], msg: "m" },
    ]);
    expect(errorDetails({ detail: "Experiment not found" })).toEqual([
      { msg: "Experiment not found" },
    ]);
    expect(errorDetails(null)).toEqual([]);
  });
});
