"use client";

import { useId } from "react";
import type { Control, FieldValues, Path } from "react-hook-form";
import { Checkbox } from "@/components/ui/checkbox";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { fieldKind, validateValue, type JsonSchema } from "@/lib/schema-form";

/** Radix Select cannot hold an empty value, so "None" uses this sentinel. */
const NONE = "__none__";

type Props<T extends FieldValues> = {
  /** react-hook-form path, e.g. `params.output_dimension`. */
  name: Path<T>;
  /** The property's JSON Schema. Label = `title`, hint = `description`. */
  schema: JsonSchema;
  control: Control<T>;
  disabled?: boolean;
};

/**
 * One form field rendered from a JSON Schema property: integer or number -> number input
 * with min, max and step; string enum -> Select; array of enum -> checkbox group; nullable
 * enum -> Select with "None"; boolean -> Checkbox. The initial value is the form's default
 * (see `initialValue`). Unknown schema shapes throw outside production so gaps show early.
 */
export function SchemaField<T extends FieldValues>({ name, schema, control, disabled }: Props<T>) {
  const kind = fieldKind(schema);
  const title = schema.title ?? name;
  const groupId = useId();

  if (!kind) {
    const message = `SchemaField: unsupported schema for "${name}": ${JSON.stringify(schema)}`;
    if (process.env.NODE_ENV !== "production") throw new Error(message);
    console.error(message);
    return null;
  }

  const hint = schema.description ? (
    <FormDescription className="text-xs">{schema.description}</FormDescription>
  ) : null;

  switch (kind.kind) {
    case "integer":
    case "number":
      return (
        <FormField
          control={control}
          name={name}
          rules={{ validate: (v) => validateValue(schema, v) }}
          render={({ field }) => (
            <FormItem className="content-start gap-1.5">
              <FormLabel>{title}</FormLabel>
              <FormControl>
                <Input
                  type="number"
                  inputMode={kind.kind === "integer" ? "numeric" : "decimal"}
                  min={kind.min}
                  max={kind.max}
                  step={kind.step}
                  className="font-mono text-xs"
                  disabled={disabled}
                  {...field}
                  value={(field.value as string | null) ?? ""}
                />
              </FormControl>
              {hint}
              <FormMessage className="text-xs" />
            </FormItem>
          )}
        />
      );

    case "enum":
    case "nullable-enum": {
      const nullable = kind.kind === "nullable-enum";
      return (
        <FormField
          control={control}
          name={name}
          render={({ field }) => {
            const value =
              field.value === null || field.value === undefined ? NONE : String(field.value);
            return (
              <FormItem className="content-start gap-1.5">
                <FormLabel>{title}</FormLabel>
                <Select
                  value={value}
                  onValueChange={(v) => field.onChange(nullable && v === NONE ? null : v)}
                  disabled={disabled}
                  name={field.name}
                >
                  <FormControl>
                    <SelectTrigger
                      className="w-full font-mono text-xs"
                      onBlur={field.onBlur}
                      ref={field.ref}
                    >
                      <SelectValue>{value === NONE ? "None" : value}</SelectValue>
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {nullable && (
                      <SelectItem value={NONE} className="text-xs">
                        None
                      </SelectItem>
                    )}
                    {kind.options.map((o) => (
                      <SelectItem key={o} value={o} className="font-mono text-xs">
                        {o}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {hint}
                <FormMessage className="text-xs" />
              </FormItem>
            );
          }}
        />
      );
    }

    case "multi-enum":
      return (
        <FormField
          control={control}
          name={name}
          render={({ field, fieldState }) => {
            const selected: string[] = Array.isArray(field.value) ? field.value : [];
            const toggle = (option: string, on: boolean) =>
              // Keep the schema's option order, whatever order the boxes are ticked in.
              field.onChange(
                kind.options.filter((o) => (o === option ? on : selected.includes(o))),
              );
            return (
              <FormItem className="content-start gap-1.5">
                <div role="group" aria-labelledby={`${groupId}-label`} className="grid gap-1.5">
                  <span id={`${groupId}-label`} className="text-sm leading-none font-medium">
                    {title}
                  </span>
                  <div className="flex flex-wrap gap-x-5 gap-y-2 pt-1">
                    {kind.options.map((o, i) => (
                      <div key={o} className="flex items-center gap-2">
                        <Checkbox
                          id={`${groupId}-${i}`}
                          checked={selected.includes(o)}
                          onCheckedChange={(v) => toggle(o, v === true)}
                          onBlur={field.onBlur}
                          ref={i === 0 ? field.ref : undefined}
                          disabled={disabled}
                          aria-invalid={!!fieldState.error}
                        />
                        <Label
                          htmlFor={`${groupId}-${i}`}
                          className="font-mono text-xs font-normal"
                        >
                          {o}
                        </Label>
                      </div>
                    ))}
                  </div>
                </div>
                {hint}
                <FormMessage className="text-xs" />
              </FormItem>
            );
          }}
        />
      );

    case "boolean":
      return (
        <FormField
          control={control}
          name={name}
          render={({ field }) => (
            <FormItem className="content-start gap-1.5">
              <div className="flex items-center gap-2">
                <FormControl>
                  <Checkbox
                    checked={field.value === true}
                    onCheckedChange={(v) => field.onChange(v === true)}
                    onBlur={field.onBlur}
                    ref={field.ref}
                    disabled={disabled || kind.locked}
                  />
                </FormControl>
                <FormLabel className="font-normal">{title}</FormLabel>
              </div>
              {hint}
              <FormMessage className="text-xs" />
            </FormItem>
          )}
        />
      );
  }
}
