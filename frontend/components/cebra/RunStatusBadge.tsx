"use client";

import { Check } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { Run } from "@/lib/api";
import { cn } from "@/lib/utils";

const BASE =
  "inline-flex h-6 items-center gap-1 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap";

/**
 * Queued (dashed grey outline), Running (blue, with `done/total`), Succeeded (zinc with a
 * check), Failed (red; click opens the full error). The text is always there, so status is
 * never shown by colour alone.
 */
export function RunStatusBadge({
  run,
}: {
  run: Pick<Run, "name" | "status" | "progress" | "error">;
}) {
  switch (run.status) {
    case "queued":
      return (
        <span
          className={cn(BASE, "border-dashed border-zinc-300 bg-white text-zinc-600")}
          data-status="queued"
        >
          Queued
        </span>
      );
    case "running":
      return (
        <span
          className={cn(BASE, "border-blue-200 bg-blue-50 text-blue-600")}
          data-status="running"
        >
          Running
          <span className="font-mono">
            {run.progress.done}/{run.progress.total}
          </span>
        </span>
      );
    case "succeeded":
      return (
        <span
          className={cn(BASE, "border-zinc-200 bg-zinc-100 text-zinc-700")}
          data-status="succeeded"
        >
          <Check className="size-3" aria-hidden />
          Succeeded
        </span>
      );
    case "failed":
      return (
        <Dialog>
          <DialogTrigger asChild>
            <button
              type="button"
              className={cn(
                BASE,
                "cursor-pointer border-red-200 bg-red-50 text-red-700 outline-none hover:bg-red-100 focus-visible:ring-3 focus-visible:ring-red-200",
              )}
              data-status="failed"
              aria-label={`Failed: show the error of ${run.name}`}
            >
              Failed
            </button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-2xl">
            <DialogHeader>
              <DialogTitle>Run {run.name} failed</DialogTitle>
              <DialogDescription>The error the worker recorded.</DialogDescription>
            </DialogHeader>
            <pre className="max-h-[60vh] overflow-auto rounded-md border border-red-200 bg-red-50 p-3 font-mono text-xs whitespace-pre-wrap break-words text-red-900">
              {run.error || "No error message was recorded."}
            </pre>
          </DialogContent>
        </Dialog>
      );
  }
}
