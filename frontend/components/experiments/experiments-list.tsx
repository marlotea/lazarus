"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ExperimentDialog } from "@/components/experiments/experiment-dialog";
import { api, queryKeys } from "@/lib/api";
import { formatDate, itemsAndRuns } from "@/lib/format";

const CARD = "overflow-hidden rounded-lg border border-zinc-200 bg-white";

function NewExperimentButton() {
  return (
    <ExperimentDialog
      trigger={
        <Button>
          <Plus aria-hidden />
          New experiment
        </Button>
      }
    />
  );
}

export function ExperimentsList() {
  const { data, isPending, isError } = useQuery({
    queryKey: queryKeys.experiments,
    queryFn: api.experiments.list,
  });

  return (
    <div>
      <header className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-[26px] font-semibold tracking-tight">Experiments</h1>
        <NewExperimentButton />
      </header>

      {isPending ? (
        <div className={CARD} aria-busy="true" aria-label="Loading experiments">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              data-testid="experiment-skeleton"
              className="flex items-center justify-between gap-6 border-b border-zinc-200 px-5 py-4 last:border-b-0"
            >
              <div className="grid flex-1 gap-2">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-3.5 w-2/3" />
              </div>
              <div className="grid justify-items-end gap-2">
                <Skeleton className="h-3.5 w-24" />
                <Skeleton className="h-3.5 w-20" />
              </div>
            </div>
          ))}
        </div>
      ) : isError ? (
        <div className={`${CARD} px-5 py-10 text-center text-zinc-500`} role="alert">
          Could not load experiments. Is the API running (<code className="font-mono text-xs">make api</code>)?
        </div>
      ) : data.length === 0 ? (
        <div className={`${CARD} flex flex-col items-center gap-3 px-5 py-14 text-center`}>
          <p className="font-medium">No experiments yet</p>
          <NewExperimentButton />
        </div>
      ) : (
        <ul className={CARD}>
          {data.map((e) => (
            <li key={e.id} className="border-b border-zinc-200 last:border-b-0">
              <Link
                href={`/experiments/${e.id}`}
                className="flex items-center justify-between gap-6 px-5 py-4 hover:bg-zinc-50 focus-visible:bg-zinc-50 focus-visible:outline-none"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{e.title}</p>
                  {e.description && (
                    <p className="mt-0.5 truncate text-zinc-500">{e.description}</p>
                  )}
                </div>
                <div className="shrink-0 text-right text-[13px] text-zinc-500">
                  <p>
                    <time dateTime={e.created_at}>{formatDate(e.created_at)}</time>
                  </p>
                  <p className="mt-0.5">{itemsAndRuns(e)}</p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
