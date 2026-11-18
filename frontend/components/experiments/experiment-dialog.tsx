"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, queryKeys, type Experiment } from "@/lib/api";

export const TITLE_MAX = 200;

export const experimentFormSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, "Title is required")
    .max(TITLE_MAX, `Title must be at most ${TITLE_MAX} characters`),
  description: z.string(),
});

type FormValues = z.infer<typeof experimentFormSchema>;

/** Pull `{field: message}` out of a FastAPI 422 body (`detail[].loc = ["body", field]`). */
function fieldErrors(err: unknown): Partial<Record<keyof FormValues, string>> {
  if (!(err instanceof ApiError) || err.status !== 422) return {};
  const detail = (err.body as { detail?: unknown } | null)?.detail;
  const out: Partial<Record<keyof FormValues, string>> = {};
  if (!Array.isArray(detail)) return out;
  for (const d of detail as { loc?: unknown[]; msg?: string }[]) {
    const field = d.loc?.[1];
    if (field === "title" || field === "description") out[field] = d.msg ?? "Invalid value";
  }
  return out;
}

type Props = {
  /** Without an experiment the dialog creates one; with one it edits it. */
  experiment?: Experiment;
  trigger: React.ReactNode;
};

export function ExperimentDialog({ experiment, trigger }: Props) {
  const editing = experiment !== undefined;
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const queryClient = useQueryClient();

  const form = useForm<FormValues>({
    resolver: zodResolver(experimentFormSchema),
    defaultValues: { title: "", description: "" },
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      editing ? api.experiments.update(experiment.id, values) : api.experiments.create(values),
    onSuccess: (saved) => {
      queryClient.setQueryData(queryKeys.experiment(saved.id), saved);
      void queryClient.invalidateQueries({ queryKey: queryKeys.experiments, exact: true });
      setOpen(false);
      if (editing) {
        toast.success("Experiment saved");
      } else {
        router.push(`/experiments/${saved.id}`);
      }
    },
    onError: (err) => {
      const errors = fieldErrors(err);
      for (const [field, message] of Object.entries(errors)) {
        form.setError(field as keyof FormValues, { message });
      }
      if (Object.keys(errors).length === 0) {
        toast.error(editing ? "Could not save the experiment" : "Could not create the experiment");
      }
    },
  });

  function onOpenChange(next: boolean) {
    if (next) {
      // Prefill on every open, so an edit starts from the current values.
      form.reset({ title: experiment?.title ?? "", description: experiment?.description ?? "" });
      mutation.reset();
    }
    setOpen(next);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
            className="grid gap-4"
            noValidate
          >
            <DialogHeader>
              <DialogTitle>{editing ? "Edit experiment" : "New experiment"}</DialogTitle>
              <DialogDescription>
                {editing
                  ? "Change the title or description."
                  : "Name the experiment. You pick its data on the next page."}
              </DialogDescription>
            </DialogHeader>
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Title</FormLabel>
                  <FormControl>
                    <Input placeholder="Control 01: CA1 across sessions" autoFocus {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Description <span className="font-normal text-zinc-500">(optional)</span>
                  </FormLabel>
                  <FormControl>
                    <Textarea rows={3} placeholder="What is this experiment for?" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending && <Loader2 className="animate-spin" aria-hidden />}
                {editing ? "Save" : "Create experiment"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
