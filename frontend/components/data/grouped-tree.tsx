"use client";

import { Checkbox as CheckboxPrimitive } from "radix-ui";
import { CheckIcon, ChevronRight, MinusIcon } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";
import {
  GROUP_BY_OPTIONS,
  groupCountLabel,
  type GroupBy,
  type GroupNode,
  type GroupableItem,
} from "@/lib/group-items";

/** Groups start open when there are fewer than this many top-level groups. */
export const OPEN_GROUPS_BELOW = 20;

/** `Group by: [Subject] [Session] [Region]`. Always keeps one option pressed. */
export function GroupByToggle({
  value,
  onChange,
}: {
  value: GroupBy;
  onChange: (by: GroupBy) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-zinc-500" id="group-by-label">
        Group by:
      </span>
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        spacing={0}
        value={value}
        onValueChange={(v) => v && onChange(v as GroupBy)}
        aria-labelledby="group-by-label"
      >
        {GROUP_BY_OPTIONS.map((o) => (
          <ToggleGroupItem key={o.value} value={o.value} className="px-3">
            {o.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}

/** Region chip: acronym + good-unit count. */
export function RegionChip({ region, units }: { region: string; units: number }) {
  return (
    <span
      className="inline-flex h-6 items-center gap-1.5 rounded-md border border-zinc-200 bg-zinc-50 px-2 text-[13px]"
      data-testid="region-chip"
    >
      <span className="font-medium">{region}</span>
      <span className="font-mono text-xs text-zinc-500">{units} units</span>
    </span>
  );
}

/** Checkbox with a real indeterminate state (shows a dash). */
export function TreeCheckbox({
  checked,
  onCheckedChange,
  className,
  ...props
}: Omit<React.ComponentProps<typeof CheckboxPrimitive.Root>, "onCheckedChange"> & {
  checked: boolean | "indeterminate";
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <CheckboxPrimitive.Root
      checked={checked}
      onCheckedChange={(v) => onCheckedChange(v === true)}
      className={cn(
        "flex size-4 shrink-0 items-center justify-center rounded-[4px] border border-zinc-300 bg-white outline-none focus-visible:ring-3 focus-visible:ring-ring/50 data-[state=checked]:border-zinc-900 data-[state=checked]:bg-zinc-900 data-[state=checked]:text-white data-[state=indeterminate]:border-zinc-900 data-[state=indeterminate]:bg-zinc-900 data-[state=indeterminate]:text-white",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="grid place-content-center">
        {checked === "indeterminate" ? (
          <MinusIcon className="size-3.5" />
        ) : (
          <CheckIcon className="size-3.5" />
        )}
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

type TreeProps<T extends GroupableItem> = {
  nodes: GroupNode<T>[];
  /** Whether groups at this depth (0 = top level) start open. */
  defaultOpen: (depth: number) => boolean;
  /** Rows under a deepest group. Called only while the group is open. */
  renderLeaves: (node: GroupNode<T>) => React.ReactNode;
  /** Before the group's toggle, e.g. a checkbox. */
  renderStart?: (node: GroupNode<T>) => React.ReactNode;
  /** Right side of the group row, e.g. a split badge. */
  renderEnd?: (node: GroupNode<T>) => React.ReactNode;
};

/** Collapsible group rows from `groupItems`. Closed groups do not render their contents. */
export function GroupedTree<T extends GroupableItem>(props: TreeProps<T>) {
  return (
    <ul className="grid gap-0.5" role="list">
      {props.nodes.map((n) => (
        <GroupRow key={n.key} node={n} depth={0} {...props} />
      ))}
    </ul>
  );
}

function GroupRow<T extends GroupableItem>({
  node,
  depth,
  ...props
}: TreeProps<T> & { node: GroupNode<T>; depth: number }) {
  return (
    <li>
      <Collapsible defaultOpen={props.defaultOpen(depth)} data-testid={`group-${node.kind}`}>
        <div className="flex min-h-8 flex-wrap items-center gap-x-2 gap-y-1 py-0.5">
          {props.renderStart?.(node)}
          <CollapsibleTrigger className="group flex min-w-0 items-center gap-1.5 rounded-sm text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
            <ChevronRight
              aria-hidden
              className="size-4 shrink-0 text-zinc-400 transition-transform group-data-[state=open]:rotate-90"
            />
            <span className={cn("truncate", depth === 0 ? "font-semibold" : "font-medium")}>
              {node.label}
            </span>
            <span className="shrink-0 text-[13px] text-zinc-500">({groupCountLabel(node)})</span>
          </CollapsibleTrigger>
          {props.renderEnd && <div className="ml-auto">{props.renderEnd(node)}</div>}
        </div>
        <CollapsibleContent className="pb-1 pl-[22px]">
          {node.children.length > 0 ? (
            <ul className="grid gap-0.5" role="list">
              {node.children.map((c) => (
                <GroupRow key={c.key} node={c} depth={depth + 1} {...props} />
              ))}
            </ul>
          ) : (
            props.renderLeaves(node)
          )}
        </CollapsibleContent>
      </Collapsible>
    </li>
  );
}
