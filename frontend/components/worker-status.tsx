"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { isWorkerOnline } from "@/lib/worker";
import { cn } from "@/lib/utils";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 5_000,
    retry: false,
    // An unreachable API is shown as "Worker offline" here, not as a toast.
    meta: { silent: true },
  });
}

/** Sidebar footer dot: green "Worker online" if the last heartbeat is under 15 s old. */
export function WorkerStatus() {
  const { data, dataUpdatedAt, isError } = useHealth();
  // Compare against the fetch time: it changes on every poll, so the dot re-renders even when
  // the heartbeat value itself has not moved.
  const online = !isError && isWorkerOnline(data?.worker_last_seen, dataUpdatedAt);

  return (
    <div className="flex items-center gap-2 px-1 text-xs text-zinc-500" role="status">
      <span
        className={cn("size-2 rounded-full", online ? "bg-green-500" : "bg-zinc-300")}
        aria-hidden
      />
      {online ? "Worker online" : "Worker offline"}
    </div>
  );
}
