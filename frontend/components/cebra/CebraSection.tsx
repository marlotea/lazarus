"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SectionHeading } from "@/components/section-heading";
import { RunsTable } from "@/components/cebra/RunsTable";
import { useHealth } from "@/components/worker-status";
import { api, queryKeys, type Experiment, type Run } from "@/lib/api";
import { isWorkerOnline } from "@/lib/worker";

const CARD = "rounded-lg border border-zinc-200 bg-white";

export const RUNS_POLL_MS = 3_000;

const isActive = (runs: Run[] | undefined) =>
  !!runs?.some((r) => r.status === "queued" || r.status === "running");

function NewRunButton({ experiment }: { experiment: Experiment }) {
  const label = (
    <>
      <Plus aria-hidden />
      New run
    </>
  );
  if (experiment.item_count > 0) {
    return (
      <Button asChild>
        <Link href={`/experiments/${experiment.id}/runs/new`}>{label}</Link>
      </Button>
    );
  }
  // A disabled button gets no pointer events, so the tooltip hangs on a focusable wrapper.
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="inline-flex rounded-lg" data-testid="new-run-disabled">
          <Button disabled>{label}</Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>Select data first</TooltipContent>
    </Tooltip>
  );
}

/** Section 2 of the experiment page: the runs table and the New run button. */
export function CebraSection({ experiment }: { experiment: Experiment }) {
  const schema = useQuery({
    queryKey: queryKeys.cebraSchema,
    queryFn: api.cebraSchema,
    staleTime: Infinity,
  });
  const runs = useQuery({
    queryKey: queryKeys.runs(experiment.id),
    queryFn: () => api.experiments.runs(experiment.id),
    // Poll only while something can still change.
    refetchInterval: (query) => (isActive(query.state.data) ? RUNS_POLL_MS : false),
  });
  const health = useHealth();
  const workerOnline =
    !health.isError && isWorkerOnline(health.data?.worker_last_seen, health.dataUpdatedAt);
  const waiting =
    health.isFetched && !workerOnline && !!runs.data?.some((r) => r.status === "queued");

  return (
    <section aria-labelledby="cebra-heading">
      <SectionHeading n={2} id="cebra-heading" action={<NewRunButton experiment={experiment} />}>
        CEBRA training
      </SectionHeading>

      {waiting && (
        <div
          role="status"
          className="mb-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-amber-900"
          data-testid="worker-offline-warning"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            The worker is not running, so queued runs will wait. Start it with{" "}
            <code className="rounded bg-amber-100 px-1 font-mono text-xs">make worker</code>.
          </p>
        </div>
      )}

      <div className={CARD}>
        {runs.isPending || schema.isPending ? (
          <div className="grid gap-3 px-5 py-4" aria-busy="true" aria-label="Loading runs">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-2/3" />
          </div>
        ) : runs.isError || schema.isError ? (
          <p role="alert" className="px-5 py-8 text-center text-red-700">
            Could not load the runs.
          </p>
        ) : runs.data.length === 0 ? (
          <p className="px-5 py-8 text-center text-zinc-500">No runs yet.</p>
        ) : (
          <RunsTable runs={runs.data} schema={schema.data} />
        )}
      </div>
    </section>
  );
}
