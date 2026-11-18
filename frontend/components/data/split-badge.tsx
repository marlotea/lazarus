"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api, errorMessage, queryKeys, type Split } from "@/lib/api";

/** `Split A 301 · B 302` with the seed in a tooltip, plus a reshuffle button. */
export function SplitBadge({
  experimentId,
  eid,
  split,
}: {
  experimentId: string;
  eid: string;
  split: Split | null;
}) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const reshuffle = useMutation({
    mutationFn: () => api.experiments.reshuffle(experimentId, eid),
    onSuccess: async (s) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.items(experimentId) });
      setOpen(false);
      toast.success(`New split: A ${s.n_a} · B ${s.n_b}`);
    },
    onError: (err) => toast.error(errorMessage(err, "Could not make a new split")),
  });

  if (!split) return <span className="text-xs text-zinc-500">No split</span>;

  return (
    <span className="inline-flex items-center gap-0.5" data-testid="split">
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            tabIndex={0}
            className="inline-flex h-6 items-center gap-1 rounded-full border border-zinc-200 bg-zinc-50 px-2.5 text-xs whitespace-nowrap text-zinc-700 outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            data-testid="split-badge"
            data-seed={split.seed}
          >
            Split A <span className="font-mono">{split.n_a}</span> · B{" "}
            <span className="font-mono">{split.n_b}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent>
          Seed <span className="font-mono">{split.seed}</span> · trials split at random, seeded
        </TooltipContent>
      </Tooltip>
      <Dialog open={open} onOpenChange={(next) => !reshuffle.isPending && setOpen(next)}>
        <DialogTrigger asChild>
          <Button variant="ghost" size="icon-xs" aria-label="Reshuffle split">
            <RefreshCw aria-hidden />
          </Button>
        </DialogTrigger>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Reshuffle split</DialogTitle>
            <DialogDescription>
              Make a new random split for this session? Runs already queued keep the old split.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline" disabled={reshuffle.isPending}>
                Cancel
              </Button>
            </DialogClose>
            <Button onClick={() => reshuffle.mutate()} disabled={reshuffle.isPending}>
              {reshuffle.isPending && <Loader2 className="animate-spin" aria-hidden />}
              Reshuffle
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </span>
  );
}
