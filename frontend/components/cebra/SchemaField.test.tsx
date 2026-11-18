import { renderToStaticMarkup } from "react-dom/server";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";
import { Form } from "@/components/ui/form";
import { SchemaField } from "@/components/cebra/SchemaField";
import { initialValue, type JsonSchema } from "@/lib/schema-form";

function Harness({ schema }: { schema: JsonSchema }) {
  const form = useForm({ defaultValues: { field: initialValue(schema) } });
  return (
    <Form {...form}>
      <SchemaField name="field" schema={schema} control={form.control} />
    </Form>
  );
}

const render = (schema: JsonSchema) => renderToStaticMarkup(<Harness schema={schema} />);

/** Attributes of the first element matching `tag` whose markup contains `marker`. */
function element(html: string, tag: string, marker = ""): string {
  const match = [...html.matchAll(new RegExp(`<${tag}\\b[^>]*>`, "g"))].find((m) =>
    m[0].includes(marker),
  );
  expect(match, `<${tag}> with ${marker}`).toBeDefined();
  return match![0];
}

describe("SchemaField", () => {
  it("renders an integer as a number input with min, max, step and the default", () => {
    const html = render({
      type: "integer",
      title: "Output dimension",
      description: "Size of the embedding.",
      default: 8,
      minimum: 2,
      maximum: 64,
    });
    const input = element(html, "input");
    expect(input).toContain('type="number"');
    expect(input).toContain('min="2"');
    expect(input).toContain('max="64"');
    expect(input).toContain('step="1"');
    expect(input).toContain('value="8"');
    expect(html).toContain("Output dimension</label>");
    expect(html).toContain("Size of the embedding.");
    // The label points at the input.
    const id = /id="([^"]+)"/.exec(input)![1];
    expect(html).toContain(`for="${id}"`);
  });

  it("renders a float with step any", () => {
    const html = render({ type: "number", title: "Learning rate", default: 0.0003, minimum: 1e-6 });
    const input = element(html, "input");
    expect(input).toContain('step="any"');
    expect(input).toContain('min="0.000001"');
    expect(input).toContain('value="0.0003"');
  });

  it("renders a string enum as a Select showing the default", () => {
    const html = render({
      type: "string",
      title: "Distance",
      enum: ["cosine", "euclidean"],
      default: "cosine",
    });
    const trigger = element(html, "button", 'role="combobox"');
    expect(trigger).toContain('aria-expanded="false"');
    expect(html).toMatch(/<span[^>]*data-slot="select-value"[^>]*>cosine<\/span>/);
    expect(html).toContain("Distance</label>");
  });

  it("renders an array of enum as a checkbox group", () => {
    const html = render({
      type: "array",
      title: "Continuous labels",
      items: { type: "string", enum: ["wheel_velocity", "signed_contrast"] },
      default: ["wheel_velocity"],
    });
    expect(element(html, "div", 'role="group"')).toContain("aria-labelledby");
    const boxes = [...html.matchAll(/<button[^>]*role="checkbox"[^>]*>/g)].map((m) => m[0]);
    expect(boxes).toHaveLength(2);
    expect(boxes[0]).toContain('aria-checked="true"');
    expect(boxes[1]).toContain('aria-checked="false"');
    expect(html).toContain("wheel_velocity</label>");
    expect(html).toContain("signed_contrast</label>");
  });

  it('renders a nullable enum as a Select with "None"', () => {
    const html = render({
      title: "Discrete label",
      anyOf: [{ type: "string", enum: ["choice", "feedback"] }, { type: "null" }],
      default: null,
    });
    element(html, "button", 'role="combobox"');
    expect(html).toMatch(/<span[^>]*data-slot="select-value"[^>]*>None<\/span>/);
  });

  it("renders a boolean as a Checkbox, disabled when locked", () => {
    const free = element(render({ type: "boolean", title: "Flag", default: false }), "button");
    expect(free).toContain('role="checkbox"');
    expect(free).toContain('aria-checked="false"');
    expect(free).not.toContain('disabled=""');

    const html = render({ type: "boolean", title: "Good units only", const: true, default: true });
    const locked = element(html, "button");
    expect(locked).toContain('aria-checked="true"');
    expect(locked).toContain('disabled=""');
    expect(html).toContain("Good units only</label>");
  });

  it("throws on an unsupported schema outside production", () => {
    expect(() => render({ type: "object", title: "Nested" })).toThrow(/unsupported schema/);
  });
});
