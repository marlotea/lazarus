"use client";

import { useMemo } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RunStatusBadge } from "@/components/cebra/RunStatusBadge";
import type { CebraSchema, Run } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { formatParam, modeLabel, schemaColumns, type JsonSchema } from "@/lib/schema-form";
import { cn } from "@/lib/utils";

// Run name and Status stay put on horizontal scroll. The name column has a fixed width so
// the status column knows its left offset; the inset shadow marks the sticky edge.
const STICKY = "sticky z-10 bg-white";
const NAME_COL = cn(STICKY, "left-0 w-[160px] min-w-[160px] max-w-[160px] pl-5");
const STATUS_COL = cn(STICKY, "left-[160px] shadow-[inset_-1px_0_0_var(--color-zinc-200)] pr-4");

function Cell({ value, present }: { value: unknown; present: boolean }) {
  if (!present) {
    return (
      <TableCell className="text-zinc-400">
        <span aria-hidden>—</span>
        <span className="sr-only">not used by this mode</span>
      </TableCell>
    );
  }
  return (
    <TableCell className="font-mono text-xs whitespace-nowrap">{formatParam(value)}</TableCell>
  );
}

/**
 * Runs, newest first. Columns: Run name, Status, Mode, one column per CEBRA parameter (the
 * ordered union of every mode's schema, titled from the schema), the preprocessing fields,
 * then Created. A parameter a run's mode does not use shows "—".
 */
export function RunsTable({ runs, schema }: { runs: Run[]; schema: CebraSchema }) {
  const { paramCols, preCols } = useMemo(
    () => ({
      paramCols: schemaColumns([
        schema.modes.time as JsonSchema,
        schema.modes.behaviour as JsonSchema,
        schema.modes.hybrid as JsonSchema,
      ]),
      preCols: schemaColumns([schema.preprocess as JsonSchema]),
    }),
    [schema],
  );

  return (
    <Table data-testid="runs-table">
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className={NAME_COL}>Run name</TableHead>
          <TableHead className={STATUS_COL}>Status</TableHead>
          <TableHead className="pl-4">Mode</TableHead>
          {paramCols.map((c) => (
            <TableHead key={`p.${c.key}`} data-param={c.key}>
              {c.title}
            </TableHead>
          ))}
          {preCols.map((c) => (
            <TableHead key={`pre.${c.key}`} data-preprocess={c.key}>
              {c.title}
            </TableHead>
          ))}
          <TableHead className="pr-5">Created</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((run) => (
          <TableRow key={run.id} data-run={run.name} className="group hover:bg-transparent">
            <TableCell className={cn(NAME_COL, "truncate font-medium")} title={run.name}>
              {run.name}
            </TableCell>
            <TableCell className={STATUS_COL}>
              <RunStatusBadge run={run} />
            </TableCell>
            <TableCell className="pl-4">{modeLabel(run.mode)}</TableCell>
            {paramCols.map((c) => (
              <Cell key={c.key} value={run.params[c.key]} present={c.key in run.params} />
            ))}
            {preCols.map((c) => (
              <Cell key={c.key} value={run.preprocess[c.key]} present={c.key in run.preprocess} />
            ))}
            <TableCell className="pr-5 font-mono text-xs whitespace-nowrap text-zinc-500">
              {formatDateTime(run.created_at)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
