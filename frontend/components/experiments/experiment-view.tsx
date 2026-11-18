"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ExperimentDialog } from "@/components/experiments/experiment-dialog";
import { SectionHeading } from "@/components/section-heading";
import { ApiError, api, queryKeys } from "@/lib/api";
import { experimentMeta } from "@/lib/format";

const CARD = "rounded-lg border border-zinc-200 bg-white";

function Breadcrumb({ title }: { title?: string }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-2 flex min-w-0 items-center gap-1.5 text-zinc-500">
      <Link href="/experiments" className="hover:text-zinc-950">
        Experiments
      </Link>
      <span aria-hidden>/</span>
      {title === undefined ? (
        <Skeleton className="h-3.5 w-32" />
      ) : (
        <span aria-current="page" className="truncate text-zinc-950">
          {title}
        </span>
      )}
    </nav>
  );
}

export function ExperimentHeaderSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading experiment">
      <Breadcrumb />
      <Skeleton className="mt-1 h-8 w-2/3" />
      <Skeleton className="mt-3 h-4 w-1/2" />
      <Skeleton className="mt-3 h-3.5 w-72" />
    </div>
  );
}

export function ExperimentView({ id }: { id: string }) {
  const { data: exp, isPending, error } = useQuery({
    queryKey: queryKeys.experiment(id),
    queryFn: () => api.experiments.get(id),
    retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
  });

  if (isPending) return <ExperimentHeaderSkeleton />;

  if (error) {
    const missing = error instanceof ApiError && (error.status === 404 || error.status === 422);
    return (
      <div>
        <Breadcrumb title={missing ? "Not found" : "Error"} />
        <div className={`${CARD} px-5 py-10 text-center`} role="alert">
          <p className="font-medium">
            {missing ? "Experiment not found" : "Could not load this experiment"}
          </p>
          <Link href="/experiments" className="mt-2 inline-block text-zinc-500 underline">
            Back to experiments
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div>
      <header className="mb-8">
        <Breadcrumb title={exp.title} />
        <div className="flex items-start justify-between gap-4">
          <h1 className="min-w-0 text-[26px] leading-tight font-semibold tracking-tight break-words">
            {exp.title}
          </h1>
          <ExperimentDialog
            experiment={exp}
            trigger={
              <Button variant="outline">
                <Pencil aria-hidden />
                Edit
              </Button>
            }
          />
        </div>
        {exp.description && (
          <p className="mt-2 whitespace-pre-line text-zinc-600">{exp.description}</p>
        )}
        <p className="mt-2 text-[13px] text-zinc-500" data-testid="experiment-meta">
          {experimentMeta(exp)}
        </p>
      </header>

      <section aria-labelledby="data-heading" className="mb-8">
        <SectionHeading n={1} id="data-heading">
          Data
        </SectionHeading>
        <div className={`${CARD} px-5 py-8 text-center text-zinc-500`}>
          {/* Filled in M4: grouped items, splits and the selection editor. */}
          No data selected yet
        </div>
      </section>

      <section aria-labelledby="cebra-heading">
        <SectionHeading n={2} id="cebra-heading">
          CEBRA training
        </SectionHeading>
        <div className={`${CARD} px-5 py-8 text-center text-zinc-500`}>
          {/* Filled in M5: runs table and the New run button. */}
          No runs yet.
        </div>
      </section>
    </div>
  );
}
