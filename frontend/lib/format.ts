import { format, parseISO } from "date-fns";

/** `2026-11-04T18:20:00+00:00` -> `Nov 4, 2026`, in the viewer's local time zone. */
export function formatDate(iso: string): string {
  return format(parseISO(iso), "MMM d, yyyy");
}

/** `plural(1, "item")` -> `1 item`; `plural(3, "item")` -> `3 items`. */
export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

type Counts = { item_count: number; session_count: number; run_count: number };

/** List row: `6 items · 3 runs`. */
export function itemsAndRuns(e: Counts): string {
  return `${plural(e.item_count, "item")} · ${plural(e.run_count, "run")}`;
}

/** Experiment header: `Created Nov 4, 2026 · 6 items in 3 sessions · 3 runs`. */
export function experimentMeta(e: Counts & { created_at: string }): string {
  return [
    `Created ${formatDate(e.created_at)}`,
    `${plural(e.item_count, "item")} in ${plural(e.session_count, "session")}`,
    plural(e.run_count, "run"),
  ].join(" · ");
}
