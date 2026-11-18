"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm, useWatch, type FieldErrors } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { SchemaField } from "@/components/cebra/SchemaField";
import { ApiError, api, queryKeys, type CebraSchema, type Experiment } from "@/lib/api";
import { plural } from "@/lib/format";
import {
  MODES,
  errorDetails,
  fieldFromLoc,
  initialValue,
  nextRunName,
  preprocessSummary,
  toSubmitObject,
  type FieldValue,
  type JsonSchema,
  type Mode,
} from "@/lib/schema-form";
import { cn } from "@/lib/utils";

const CARD = "rounded-lg border border-zinc-200 bg-white";
const NAME_MAX = 100;
export const DUPLICATE_NAME = "Name already used in this experiment";

type FormValues = {
  name: string;
  mode: Mode;
  params: Record<string, FieldValue>;
  preprocess: Record<string, FieldValue>;
};

function Breadcrumb({ experiment }: { experiment?: Experiment }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-2 flex min-w-0 items-center gap-1.5 text-zinc-500">
      <Link href="/experiments" className="hover:text-zinc-950">
        Experiments
      </Link>
      <span aria-hidden>/</span>
      {experiment ? (
        <Link href={`/experiments/${experiment.id}`} className="truncate hover:text-zinc-950">
          {experiment.title}
        </Link>
      ) : (
        <Skeleton className="h-3.5 w-32" />
      )}
      <span aria-hidden>/</span>
      <span aria-current="page" className="shrink-0 text-zinc-950">
        New run
      </span>
    </nav>
  );
}

export function NewRunSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading">
      <Breadcrumb />
      <Skeleton className="mt-1 mb-6 h-8 w-40" />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <Skeleton className="h-96 rounded-lg" />
        <Skeleton className="h-48 rounded-lg" />
      </div>
    </div>
  );
}

/** `/experiments/[id]/runs/new`: loads what the form needs, then renders it. */
export function NewRunForm({ id }: { id: string }) {
  const experiment = useQuery({
    queryKey: queryKeys.experiment(id),
    queryFn: () => api.experiments.get(id),
  });
  const schema = useQuery({
    queryKey: queryKeys.cebraSchema,
    queryFn: api.cebraSchema,
    staleTime: Infinity,
  });
  const runs = useQuery({
    queryKey: queryKeys.runs(id),
    queryFn: () => api.experiments.runs(id),
  });
  // Next.js hides a page with <Activity> instead of unmounting it, which would keep the last
  // draft. A new run starts fresh on every visit: remount the form when the page is hidden.
  const [visit, setVisit] = useState(0);
  useLayoutEffect(() => () => setVisit((v) => v + 1), []);

  if (experiment.isError || schema.isError || runs.isError) {
    const missing = experiment.error instanceof ApiError && experiment.error.status < 500;
    return (
      <div>
        <Breadcrumb experiment={experiment.data} />
        <div className={`${CARD} px-5 py-10 text-center`} role="alert">
          <p className="font-medium">
            {missing ? "Experiment not found" : "Could not load the run form"}
          </p>
          <Link href="/experiments" className="mt-2 inline-block text-zinc-500 underline">
            Back to experiments
          </Link>
        </div>
      </div>
    );
  }
  if (!experiment.data || !schema.data || !runs.data) return <NewRunSkeleton />;

  return (
    <NewRunFormBody
      key={visit}
      experiment={experiment.data}
      schema={schema.data}
      runNames={runs.data.map((r) => r.name)}
    />
  );
}

function Section({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  const id = `section-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <section aria-labelledby={id} className={cn("border-b border-zinc-200 px-5 py-5", className)}>
      <h2 id={id} className="mb-3 text-[15px] font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

function NewRunFormBody({
  experiment,
  schema,
  runNames,
}: {
  experiment: Experiment;
  schema: CebraSchema;
  runNames: string[];
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const modeSchemas = schema.modes as Record<Mode, JsonSchema>;
  const preSchema = schema.preprocess as JsonSchema;
  const preProps = Object.entries(preSchema.properties ?? {});

  // Form state holds every mode's params, so a value typed in one mode survives a switch.
  const defaultValues = useMemo<FormValues>(() => {
    const params: Record<string, FieldValue> = {};
    for (const m of MODES) {
      for (const [key, s] of Object.entries(modeSchemas[m.value].properties ?? {})) {
        if (!(key in params)) params[key] = initialValue(s);
      }
    }
    const preprocess = Object.fromEntries(preProps.map(([k, s]) => [k, initialValue(s)]));
    return { name: nextRunName("time", runNames), mode: "time", params, preprocess };
    // Computed once, on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const form = useForm<FormValues>({ defaultValues });
  const mode = useWatch({ control: form.control, name: "mode" });
  const preValues = useWatch({ control: form.control, name: "preprocess" });
  const nameEdited = useRef(false);
  const [preOpen, setPreOpen] = useState(false);

  // Keep the suggested name free when the runs list refreshes, unless the user typed one.
  const takenNames = runNames.join("\n");
  useEffect(() => {
    if (!nameEdited.current) form.setValue("name", nextRunName(form.getValues("mode"), runNames));
    // runNames is a new array each render; its content is tracked by takenNames.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [takenNames, form]);

  const modeProps = Object.entries(modeSchemas[mode].properties ?? {});
  const labelProps = modeProps.filter(([, s]) => s["x-group"] === "labels");
  const modelProps = modeProps.filter(([, s]) => s["x-group"] !== "labels");
  const modeInfo = MODES.find((m) => m.value === mode)!;

  const nItems = experiment.item_count;

  function changeMode(next: Mode) {
    form.setValue("mode", next);
    if (!nameEdited.current) {
      form.setValue("name", nextRunName(next, runNames));
      form.clearErrors("name");
    }
  }

  function isFormField(field: string): field is keyof FormValues | `params.${string}` {
    const [section, key] = field.split(".");
    if (field === "name" || field === "mode") return true;
    if (section === "params") return modeProps.some(([k]) => k === key);
    if (section === "preprocess") return preProps.some(([k]) => k === key);
    return false;
  }

  function showServerErrors(err: unknown) {
    if (err instanceof ApiError && err.status === 409) {
      form.setError("name", { type: "server", message: DUPLICATE_NAME }, { shouldFocus: true });
      return;
    }
    if (err instanceof ApiError && err.status === 422) {
      const other: string[] = [];
      let first = true;
      for (const d of errorDetails(err.body)) {
        const field = fieldFromLoc(d.loc);
        if (field && isFormField(field)) {
          if (field.startsWith("preprocess.")) setPreOpen(true);
          form.setError(
            field as keyof FormValues,
            { type: "server", message: d.msg ?? "Invalid value" },
            { shouldFocus: first },
          );
          first = false;
        } else {
          other.push(d.msg ?? "Invalid request");
        }
      }
      if (other.length) toast.error(other.join(". "));
      return;
    }
    toast.error("Could not queue the run");
  }

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      api.experiments.createRun(experiment.id, {
        name: values.name.trim(),
        mode: values.mode,
        params: toSubmitObject(modeSchemas[values.mode], values.params),
        preprocess: toSubmitObject(preSchema, values.preprocess),
      }),
    onSuccess: async () => {
      toast.success("Run queued");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.experiment(experiment.id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.experiments, exact: true }),
      ]);
      router.push(`/experiments/${experiment.id}`);
    },
    onError: showServerErrors,
  });

  function onInvalid(errors: FieldErrors<FormValues>) {
    if (errors.preprocess) setPreOpen(true);
  }

  return (
    <div>
      <Breadcrumb experiment={experiment} />
      <h1 className="mb-6 text-[26px] leading-tight font-semibold tracking-tight">New run</h1>

      <Form {...form}>
        <form
          onSubmit={form.handleSubmit((values) => mutation.mutate(values), onInvalid)}
          noValidate
          className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px] lg:items-start"
          data-testid="new-run-form"
        >
          <div className={CARD}>
            <Section title="Basics">
              <FormField
                control={form.control}
                name="name"
                rules={{
                  validate: (v) => {
                    const name = String(v).trim();
                    if (!name) return "Name is required";
                    if (name.length > NAME_MAX) return `At most ${NAME_MAX} characters`;
                    return true;
                  },
                }}
                render={({ field }) => (
                  <FormItem className="max-w-sm gap-1.5">
                    <FormLabel>Run name</FormLabel>
                    <FormControl>
                      <Input
                        className="font-mono text-xs"
                        autoComplete="off"
                        {...field}
                        onChange={(e) => {
                          nameEdited.current = true;
                          field.onChange(e);
                        }}
                      />
                    </FormControl>
                    <FormMessage className="text-xs" />
                  </FormItem>
                )}
              />
            </Section>

            <Section title="Mode">
              <ToggleGroup
                type="single"
                variant="outline"
                spacing={0}
                value={mode}
                onValueChange={(v) => v && changeMode(v as Mode)}
                aria-label="Mode"
                aria-describedby="mode-hint"
              >
                {MODES.map((m) => (
                  <ToggleGroupItem key={m.value} value={m.value} className="px-4">
                    {m.label}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
              <p id="mode-hint" className="mt-2 text-zinc-500" data-testid="mode-hint">
                {modeInfo.hint}
              </p>
            </Section>

            {labelProps.length > 0 && (
              <Section title="Behaviour labels">
                <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
                  {labelProps.map(([key, s]) => (
                    <SchemaField
                      key={key}
                      name={`params.${key}`}
                      schema={s}
                      control={form.control}
                    />
                  ))}
                </div>
              </Section>
            )}

            <Section title="Model and training">
              <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
                {modelProps.map(([key, s]) => (
                  <SchemaField key={key} name={`params.${key}`} schema={s} control={form.control} />
                ))}
              </div>
            </Section>

            <Collapsible open={preOpen} onOpenChange={setPreOpen}>
              <CollapsibleTrigger className="group flex w-full items-start gap-2 rounded-b-lg px-5 py-4 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
                <ChevronRight
                  className="mt-0.5 size-4 shrink-0 text-zinc-500 transition-transform group-data-[state=open]:rotate-90"
                  aria-hidden
                />
                <span className="grid min-w-0 gap-0.5 sm:flex sm:flex-1 sm:items-baseline sm:gap-3">
                  <span className="text-[15px] font-semibold">Preprocessing</span>
                  <span
                    className="truncate font-mono text-xs text-zinc-500"
                    data-testid="preprocess-summary"
                  >
                    {preprocessSummary(preValues)}
                  </span>
                </span>
              </CollapsibleTrigger>
              {/* Kept mounted while closed so its fields still validate. */}
              <CollapsibleContent forceMount className="px-5 pb-5 data-[state=closed]:hidden">
                <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
                  {preProps.map(([key, s]) => (
                    <div key={key} className={cn(s.type === "boolean" && "sm:col-span-2")}>
                      <SchemaField name={`preprocess.${key}`} schema={s} control={form.control} />
                    </div>
                  ))}
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>

          <aside className={cn(CARD, "grid gap-4 p-5 lg:sticky lg:top-7")} aria-label="Summary">
            <h2 className="text-[15px] font-semibold">Summary</h2>
            <ul className="grid gap-2 text-zinc-700" data-testid="run-summary">
              <li>
                {plural(nItems, "item")} in {plural(experiment.session_count, "session")}
              </li>
              <li>
                Trains {plural(nItems * 2, "model")} ({plural(nItems, "item")} × groups A and B)
              </li>
              <li className="text-zinc-500">Runs on the backend machine</li>
            </ul>
            {nItems === 0 && (
              <p className="text-red-700" role="alert">
                Select data first.
              </p>
            )}
            <div className="grid gap-2">
              <Button type="submit" disabled={mutation.isPending || nItems === 0}>
                {mutation.isPending && <Loader2 className="animate-spin" aria-hidden />}
                Queue run
              </Button>
              <Button variant="outline" asChild>
                <Link href={`/experiments/${experiment.id}`}>Cancel</Link>
              </Button>
            </div>
          </aside>
        </form>
      </Form>
    </div>
  );
}
