"use client";

// Placeholder until /api/health exists (M1).
export function WorkerStatus() {
  return (
    <div className="flex items-center gap-2 px-1 text-xs text-zinc-500">
      <span className="size-2 rounded-full bg-zinc-300" aria-hidden />
      Worker offline
    </div>
  );
}
