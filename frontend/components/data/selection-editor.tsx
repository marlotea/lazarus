"use client";

import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronsUpDown, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  GroupByToggle,
  GroupedTree,
  RegionChip,
  TreeCheckbox,
} from "@/components/data/grouped-tree";
import {
  ApiError,
  api,
  queryKeys,
  type CatalogItem,
  type CatalogQuery,
  type CatalogRegion,
  type ItemRef,
} from "@/lib/api";
import {
  groupItems,
  itemKey,
  selectionSummary,
  type GroupBy,
  type GroupNode,
} from "@/lib/group-items";
import { plural } from "@/lib/format";

const ALL_LABS = "__all__";
const DEBOUNCE_MS = 300;

function useDebouncedValue<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

type Props = {
  experimentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The current selection; the editor starts with these checked. */
  selected: ItemRef[];
};

/** Right-side Sheet to browse the catalog and pick session x region items. */
export function SelectionEditor({ experimentId, open, onOpenChange, selected }: Props) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-[960px]"
      >
        <SheetHeader className="border-b border-zinc-200 px-6 py-4">
          <SheetTitle className="text-base">Select data</SheetTitle>
          <SheetDescription>
            Pick session × region items. New sessions get a random split of their trials.
          </SheetDescription>
        </SheetHeader>
        {/* Mounted only while open, so each open starts from the saved selection. */}
        <EditorBody
          experimentId={experimentId}
          initial={selected}
          onDone={() => onOpenChange(false)}
        />
      </SheetContent>
    </Sheet>
  );
}

function EditorBody({
  experimentId,
  initial,
  onDone,
}: {
  experimentId: string;
  initial: ItemRef[];
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(
    () => new Map(initial.map((i) => [itemKey(i), { eid: i.eid, region: i.region }])),
  );
  const [regions, setRegions] = useState<string[]>([]);
  const [subject, setSubject] = useState("");
  const [lab, setLab] = useState(ALL_LABS);
  const [minUnits, setMinUnits] = useState("0");
  const [by, setBy] = useState<GroupBy>("subject");

  const filters = useMemo<CatalogQuery>(() => {
    const min = Math.max(0, Math.floor(Number(minUnits)) || 0);
    return {
      region: regions.length ? regions : undefined,
      subject: subject.trim() || undefined,
      lab: lab === ALL_LABS ? undefined : lab,
      min_units: min || undefined,
    };
  }, [regions, subject, lab, minUnits]);
  const query = useDebouncedValue(filters, DEBOUNCE_MS);

  const catalog = useQuery({
    queryKey: queryKeys.catalogItems(query),
    queryFn: () => api.catalogItems(query),
    placeholderData: keepPreviousData,
  });
  const regionOptions = useQuery({
    queryKey: queryKeys.catalogRegions,
    queryFn: api.catalogRegions,
  });
  // Labs come from the unfiltered catalog (same request as the editor's first fetch).
  const labs = useQuery({
    queryKey: queryKeys.catalogItems({}),
    queryFn: () => api.catalogItems({}),
    select: (rows) => [...new Set(rows.map((r) => r.lab))].sort(),
  });

  const rows = useMemo(() => catalog.data ?? [], [catalog.data]);
  const nodes = useMemo(() => groupItems(rows, by), [rows, by]);
  const hiddenSelected = useMemo(() => {
    const shown = new Set(rows.map(itemKey));
    return [...selected.keys()].filter((k) => !shown.has(k)).length;
  }, [rows, selected]);

  function setChecked(items: CatalogItem[], checked: boolean) {
    setSelected((prev) => {
      const next = new Map(prev);
      for (const i of items) {
        if (checked) next.set(itemKey(i), { eid: i.eid, region: i.region });
        else next.delete(itemKey(i));
      }
      return next;
    });
  }

  function groupState(node: GroupNode<CatalogItem>): boolean | "indeterminate" {
    let n = 0;
    for (const i of node.items) if (selected.has(itemKey(i))) n++;
    return n === 0 ? false : n === node.items.length ? true : "indeterminate";
  }

  const save = useMutation({
    mutationFn: () => api.experiments.replaceItems(experimentId, [...selected.values()]),
    onSuccess: (items) => {
      queryClient.setQueryData(queryKeys.items(experimentId), items);
      void queryClient.invalidateQueries({ queryKey: queryKeys.experiment(experimentId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.experiments, exact: true });
      toast.success("Selection saved");
      onDone();
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? (err.body as { detail?: unknown })?.detail : null;
      const message =
        typeof detail === "string"
          ? detail
          : typeof (detail as { message?: unknown })?.message === "string"
            ? (detail as { message: string }).message
            : "Could not save the selection";
      toast.error(message);
    },
  });

  const selectedList = [...selected.values()];
  // Group by subject has sessions nested inside; open those once their subject is opened.
  const defaultOpen = (depth: number) => depth > 0;

  return (
    <>
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto md:grid-cols-[260px_1fr] md:grid-rows-[minmax(0,1fr)] md:overflow-hidden">
        <aside
          className="grid content-start gap-4 border-b border-zinc-200 px-6 py-4 md:border-r md:border-b-0"
          aria-label="Filters"
        >
          <RegionFilter options={regionOptions.data ?? []} value={regions} onChange={setRegions} />
          <div className="grid gap-1.5">
            <Label htmlFor="subject-filter">Subject</Label>
            <Input
              id="subject-filter"
              type="search"
              placeholder="Search subjects"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="lab-filter">Lab</Label>
            <Select value={lab} onValueChange={setLab}>
              <SelectTrigger id="lab-filter" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_LABS}>All labs</SelectItem>
                {(labs.data ?? []).map((l) => (
                  <SelectItem key={l} value={l}>
                    {l}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="min-units-filter">Min good units</Label>
            <Input
              id="min-units-filter"
              type="number"
              min={0}
              step={1}
              inputMode="numeric"
              value={minUnits}
              onChange={(e) => setMinUnits(e.target.value)}
              className="font-mono"
            />
          </div>
        </aside>

        <div className="flex min-h-0 flex-col">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 px-6 py-3">
            <GroupByToggle value={by} onChange={setBy} />
            <span className="text-[13px] text-zinc-500" aria-live="polite">
              {catalog.isFetching ? "Loading…" : `${plural(rows.length, "catalog item")}`}
            </span>
          </div>
          <ScrollArea className="min-h-0 flex-1">
            <div className="px-6 py-3" data-testid="catalog-tree">
              {catalog.isPending ? (
                <div className="grid gap-2">
                  {[0, 1, 2, 3].map((k) => (
                    <Skeleton key={k} className="h-6 w-2/3" />
                  ))}
                </div>
              ) : catalog.isError ? (
                <p role="alert" className="text-red-700">
                  Could not load the catalog.
                </p>
              ) : rows.length === 0 ? (
                <p className="py-6 text-center text-zinc-500">No catalog items match the filters.</p>
              ) : (
                <GroupedTree
                  key={by}
                  nodes={nodes}
                  defaultOpen={defaultOpen}
                  renderStart={(node) => (
                    <TreeCheckbox
                      checked={groupState(node)}
                      onCheckedChange={(c) => setChecked(node.items, c)}
                      aria-label={`Select all in ${node.label}`}
                    />
                  )}
                  renderLeaves={(node) => (
                    <ul className="grid" role="list">
                      {node.items.map((i) => (
                        <CatalogLeaf
                          key={itemKey(i)}
                          item={i}
                          checked={selected.has(itemKey(i))}
                          onCheckedChange={(c) => setChecked([i], c)}
                        />
                      ))}
                    </ul>
                  )}
                />
              )}
              {hiddenSelected > 0 && (
                <p className="mt-3 text-[13px] text-zinc-500">
                  {plural(hiddenSelected, "selected item")} hidden by the filters.
                </p>
              )}
            </div>
          </ScrollArea>
        </div>
      </div>

      <footer className="sticky bottom-0 flex flex-wrap items-center justify-between gap-3 border-t border-zinc-200 bg-white px-6 py-3">
        <span data-testid="selection-summary">{selectionSummary(selectedList)} selected</span>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onDone} disabled={save.isPending}>
            Cancel
          </Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending && <Loader2 className="animate-spin" aria-hidden />}
            Save
          </Button>
        </div>
      </footer>
    </>
  );
}

function CatalogLeaf({
  item,
  checked,
  onCheckedChange,
}: {
  item: CatalogItem;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  const id = `leaf-${itemKey(item)}`;
  return (
    <li className="flex items-center gap-3 rounded-md py-1 pr-2 hover:bg-zinc-50">
      <TreeCheckbox
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        aria-label={`${item.region} in ${item.subject} ${item.session_date}`}
      />
      <label htmlFor={id} className="flex min-w-0 flex-1 cursor-pointer flex-wrap items-center gap-x-3 gap-y-1">
        <RegionChip region={item.region} units={item.n_good_units} />
        <span>{item.subject}</span>
        <span className="font-mono text-xs text-zinc-500">{item.session_date}</span>
        <span className="text-zinc-500">{item.lab}</span>
      </label>
    </li>
  );
}

function RegionFilter({
  options,
  value,
  onChange,
}: {
  options: CatalogRegion[];
  value: string[];
  onChange: (regions: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const toggle = (region: string) =>
    onChange(value.includes(region) ? value.filter((r) => r !== region) : [...value, region]);

  return (
    <div className="grid gap-1.5">
      <Label id="region-filter-label">Region</Label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            aria-labelledby="region-filter-label"
            className="w-full justify-between font-normal"
          >
            <span className={value.length ? "" : "text-zinc-500"}>
              {value.length ? `${plural(value.length, "region")} selected` : "Any region"}
            </span>
            <ChevronsUpDown aria-hidden className="text-zinc-400" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-(--radix-popover-trigger-width) min-w-56 p-0">
          <Command>
            <CommandInput placeholder="Search regions" />
            <CommandList>
              <CommandEmpty>No region found.</CommandEmpty>
              <CommandGroup>
                {options.map((o) => (
                  <CommandItem
                    key={o.region}
                    value={o.region}
                    data-checked={value.includes(o.region)}
                    onSelect={() => toggle(o.region)}
                  >
                    <span className="font-medium">{o.region}</span>
                    <span className="text-xs text-zinc-500">
                      {plural(o.n_sessions, "session")}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1" aria-label="Selected regions">
          {value.map((r) => (
            <span
              key={r}
              className="inline-flex h-6 items-center gap-1 rounded-md border border-zinc-200 bg-zinc-50 pr-1 pl-2 text-[13px] font-medium"
            >
              {r}
              <button
                type="button"
                aria-label={`Remove ${r}`}
                onClick={() => toggle(r)}
                className="rounded-sm text-zinc-500 hover:text-zinc-950"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
