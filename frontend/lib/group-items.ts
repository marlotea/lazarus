// Pure grouping of session x region items into a tree, shared by the data section and the
// selection editor. Subject: subject -> session -> items. Session: session -> items.
// Region: region -> items (one item per session that has the region).

import { plural } from "@/lib/format";

export type GroupBy = "subject" | "session" | "region";

export const GROUP_BY_OPTIONS: { value: GroupBy; label: string }[] = [
  { value: "subject", label: "Subject" },
  { value: "session", label: "Session" },
  { value: "region", label: "Region" },
];

/** The fields grouping needs; catalog rows and selected items both have them. */
export type GroupableItem = {
  eid: string;
  region: string;
  subject: string;
  lab: string;
  session_date: string;
  n_good_units: number;
};

export type SessionInfo = Pick<GroupableItem, "eid" | "subject" | "lab" | "session_date">;

export type GroupNode<T extends GroupableItem> = {
  kind: GroupBy;
  /** Unique within the tree, e.g. `subject:KS023/session:<eid>`. */
  key: string;
  /** Subject name, region acronym, or `2019-12-10 · cortexlab` for a session. */
  label: string;
  /** Set on session nodes. */
  session?: SessionInfo;
  /** Sub-groups (sessions under a subject). Empty on the deepest groups. */
  children: GroupNode<T>[];
  /** Every item under this node, sorted by subject, date, session, region. */
  items: T[];
  sessionCount: number;
  regionCount: number;
};

/** Stable key of one item. */
export function itemKey(item: Pick<GroupableItem, "eid" | "region">): string {
  return `${item.eid}|${item.region}`;
}

function cmp(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function compareItems(a: GroupableItem, b: GroupableItem): number {
  return (
    cmp(a.subject, b.subject) ||
    cmp(a.session_date, b.session_date) ||
    cmp(a.eid, b.eid) ||
    cmp(a.region, b.region)
  );
}

/** Group in first-seen order of the (already sorted) items. */
function bucket<T>(items: T[], keyOf: (item: T) => string): Map<string, T[]> {
  const out = new Map<string, T[]>();
  for (const item of items) {
    const k = keyOf(item);
    const list = out.get(k);
    if (list) list.push(item);
    else out.set(k, [item]);
  }
  return out;
}

function node<T extends GroupableItem>(
  kind: GroupBy,
  key: string,
  label: string,
  items: T[],
  children: GroupNode<T>[] = [],
  session?: SessionInfo,
): GroupNode<T> {
  return {
    kind,
    key,
    label,
    session,
    children,
    items,
    sessionCount: new Set(items.map((i) => i.eid)).size,
    regionCount: new Set(items.map((i) => i.region)).size,
  };
}

function sessionNodes<T extends GroupableItem>(
  items: T[],
  parentKey: string,
  withSubject: boolean,
): GroupNode<T>[] {
  return [...bucket(items, (i) => i.eid)].map(([eid, list]) => {
    const { subject, lab, session_date } = list[0];
    const label = [withSubject ? subject : null, session_date, lab].filter(Boolean).join(" · ");
    return node("session", `${parentKey}session:${eid}`, label, list, [], {
      eid,
      subject,
      lab,
      session_date,
    });
  });
}

/** Turn a flat list of items into a tree for the chosen grouping. The input is not mutated. */
export function groupItems<T extends GroupableItem>(items: readonly T[], by: GroupBy): GroupNode<T>[] {
  const sorted = [...items].sort(compareItems);
  switch (by) {
    case "subject":
      return [...bucket(sorted, (i) => i.subject)].map(([subject, list]) => {
        const key = `subject:${subject}`;
        return node("subject", key, subject, list, sessionNodes(list, `${key}/`, false));
      });
    case "session":
      return sessionNodes(sorted, "", true);
    case "region": {
      const regions = [...bucket(sorted, (i) => i.region)].sort(([a], [b]) => cmp(a, b));
      return regions.map(([region, list]) => node("region", `region:${region}`, region, list));
    }
  }
}

/** Count shown next to a group: `2 sessions, 3 regions`, `3 regions` or `4 sessions`. */
export function groupCountLabel(n: Pick<GroupNode<GroupableItem>, "kind" | "sessionCount" | "regionCount">): string {
  const sessions = plural(n.sessionCount, "session");
  const regions = plural(n.regionCount, "region");
  if (n.kind === "subject") return `${sessions}, ${regions}`;
  if (n.kind === "session") return regions;
  return sessions;
}

/** Selection summary: `8 items in 4 sessions`. */
export function selectionSummary(items: readonly Pick<GroupableItem, "eid">[]): string {
  return `${plural(items.length, "item")} in ${plural(new Set(items.map((i) => i.eid)).size, "session")}`;
}
