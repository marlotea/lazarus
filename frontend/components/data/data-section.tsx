"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { SectionHeading } from "@/components/section-heading";
import {
  GroupByToggle,
  GroupedTree,
  OPEN_GROUPS_BELOW,
  RegionChip,
} from "@/components/data/grouped-tree";
import { SelectionEditor } from "@/components/data/selection-editor";
import { SplitBadge } from "@/components/data/split-badge";
import { api, queryKeys, type ExperimentItem } from "@/lib/api";
import { groupItems, itemKey, type GroupBy, type GroupNode } from "@/lib/group-items";

const CARD = "rounded-lg border border-zinc-200 bg-white";

/** Section 1 of the experiment page: the selected items, grouped, with each session's split. */
export function DataSection({ experimentId }: { experimentId: string }) {
  const [by, setBy] = useState<GroupBy>("subject");
  const [editorOpen, setEditorOpen] = useState(false);
  const { data: items, isPending, isError } = useQuery({
    queryKey: queryKeys.items(experimentId),
    queryFn: () => api.experiments.items(experimentId),
  });
  const nodes = useMemo(() => groupItems(items ?? [], by), [items, by]);
  const open = nodes.length < OPEN_GROUPS_BELOW;

  const badge = (item: ExperimentItem) => (
    <SplitBadge experimentId={experimentId} eid={item.eid} split={item.split} />
  );

  function leaves(node: GroupNode<ExperimentItem>) {
    if (node.kind === "region") {
      // Region -> sessions: one row per session that has this region.
      return (
        <ul className="grid gap-0.5 pb-1" role="list">
          {node.items.map((i) => (
            <li key={itemKey(i)} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-0.5">
              <span className="font-medium">{i.subject}</span>
              <span className="font-mono text-xs text-zinc-500">{i.session_date}</span>
              <span className="text-zinc-500">{i.lab}</span>
              <span className="font-mono text-xs text-zinc-500">{i.n_good_units} units</span>
              <span className="ml-auto">{badge(i)}</span>
            </li>
          ))}
        </ul>
      );
    }
    return (
      <div className="flex flex-wrap gap-1.5 pt-0.5 pb-2">
        {node.items.map((i) => (
          <RegionChip key={itemKey(i)} region={i.region} units={i.n_good_units} />
        ))}
      </div>
    );
  }

  const hasItems = !!items && items.length > 0;

  return (
    <section aria-labelledby="data-heading" className="mb-8">
      <SectionHeading
        n={1}
        id="data-heading"
        action={
          hasItems && (
            <Button variant="outline" onClick={() => setEditorOpen(true)}>
              <Pencil aria-hidden />
              Edit selection
            </Button>
          )
        }
      >
        Data
      </SectionHeading>

      <div className={CARD}>
        {isPending ? (
          <div className="grid gap-3 px-5 py-4" aria-busy="true" aria-label="Loading data">
            <Skeleton className="h-7 w-64" />
            <Skeleton className="h-5 w-1/2" />
            <Skeleton className="h-5 w-1/3" />
          </div>
        ) : isError ? (
          <p role="alert" className="px-5 py-8 text-center text-red-700">
            Could not load the selected data.
          </p>
        ) : !hasItems ? (
          <div className="px-5 py-10 text-center">
            <p className="font-medium">No data selected yet</p>
            <p className="mt-1 text-zinc-500">Pick IBL sessions and brain regions to train on.</p>
            <Button className="mt-4" onClick={() => setEditorOpen(true)}>
              <Plus aria-hidden />
              Select data
            </Button>
          </div>
        ) : (
          <>
            <div className="border-b border-zinc-200 px-5 py-3">
              <GroupByToggle value={by} onChange={setBy} />
            </div>
            <div className="px-5 py-3" data-testid="data-tree">
              <GroupedTree
                key={by}
                nodes={nodes}
                defaultOpen={() => open}
                renderLeaves={leaves}
                renderEnd={(node) => node.kind === "session" && badge(node.items[0])}
              />
            </div>
          </>
        )}
      </div>

      <SelectionEditor
        experimentId={experimentId}
        open={editorOpen}
        onOpenChange={setEditorOpen}
        selected={items ?? []}
      />
    </section>
  );
}
