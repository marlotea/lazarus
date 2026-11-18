import { describe, expect, it } from "vitest";
import {
  groupCountLabel,
  groupItems,
  itemKey,
  selectionSummary,
  type GroupableItem,
  type GroupNode,
} from "@/lib/group-items";

const E1 = "11111111-0000-0000-0000-000000000001"; // KS023, 2019-12-10
const E2 = "22222222-0000-0000-0000-000000000002"; // KS023, 2019-12-12
const E3 = "33333333-0000-0000-0000-000000000003"; // CSHL049, 2020-01-08

function item(eid: string, region: string, units: number): GroupableItem {
  const meta: Record<string, [string, string, string]> = {
    [E1]: ["KS023", "cortexlab", "2019-12-10"],
    [E2]: ["KS023", "cortexlab", "2019-12-12"],
    [E3]: ["CSHL049", "churchlandlab", "2020-01-08"],
  };
  const [subject, lab, session_date] = meta[eid];
  return { eid, region, subject, lab, session_date, n_good_units: units };
}

// Deliberately unsorted input.
const ITEMS = [
  item(E2, "CA1", 52),
  item(E1, "DG", 41),
  item(E3, "PO", 18),
  item(E1, "CA1", 64),
  item(E3, "CA1", 37),
];

const keys = (list: GroupableItem[]) => list.map(itemKey);
const shape = (nodes: GroupNode<GroupableItem>[]): unknown =>
  nodes.map((n) => ({
    label: n.label,
    items: keys(n.items),
    ...(n.children.length ? { children: shape(n.children) } : {}),
  }));

describe("groupItems by subject", () => {
  const tree = groupItems(ITEMS, "subject");

  it("nests subject -> session -> items, all sorted", () => {
    expect(shape(tree)).toEqual([
      {
        label: "CSHL049",
        items: [`${E3}|CA1`, `${E3}|PO`],
        children: [{ label: "2020-01-08 · churchlandlab", items: [`${E3}|CA1`, `${E3}|PO`] }],
      },
      {
        label: "KS023",
        items: [`${E1}|CA1`, `${E1}|DG`, `${E2}|CA1`],
        children: [
          { label: "2019-12-10 · cortexlab", items: [`${E1}|CA1`, `${E1}|DG`] },
          { label: "2019-12-12 · cortexlab", items: [`${E2}|CA1`] },
        ],
      },
    ]);
  });

  it("sets kinds, unique keys, session info and counts", () => {
    const ks = tree[1];
    expect(ks.kind).toBe("subject");
    expect([ks.sessionCount, ks.regionCount]).toEqual([2, 2]);
    expect(groupCountLabel(ks)).toBe("2 sessions, 2 regions");
    expect(groupCountLabel(tree[0])).toBe("1 session, 2 regions");
    const s = ks.children[0];
    expect(s.kind).toBe("session");
    expect(s.session).toEqual({
      eid: E1,
      subject: "KS023",
      lab: "cortexlab",
      session_date: "2019-12-10",
    });
    expect(groupCountLabel(s)).toBe("2 regions");
    const allKeys = tree.flatMap((n) => [n.key, ...n.children.map((c) => c.key)]);
    expect(new Set(allKeys).size).toBe(allKeys.length);
  });
});

describe("groupItems by session", () => {
  it("makes one flat group per session, labelled with the subject", () => {
    const tree = groupItems(ITEMS, "session");
    expect(shape(tree)).toEqual([
      { label: "CSHL049 · 2020-01-08 · churchlandlab", items: [`${E3}|CA1`, `${E3}|PO`] },
      { label: "KS023 · 2019-12-10 · cortexlab", items: [`${E1}|CA1`, `${E1}|DG`] },
      { label: "KS023 · 2019-12-12 · cortexlab", items: [`${E2}|CA1`] },
    ]);
    expect(tree.every((n) => n.kind === "session" && n.children.length === 0)).toBe(true);
    expect(tree[1].session?.eid).toBe(E1);
    expect(groupCountLabel(tree[2])).toBe("1 region");
  });
});

describe("groupItems by region", () => {
  it("makes one group per region, sorted by acronym, sessions inside", () => {
    const tree = groupItems(ITEMS, "region");
    expect(shape(tree)).toEqual([
      { label: "CA1", items: [`${E3}|CA1`, `${E1}|CA1`, `${E2}|CA1`] },
      { label: "DG", items: [`${E1}|DG`] },
      { label: "PO", items: [`${E3}|PO`] },
    ]);
    expect(tree[0].kind).toBe("region");
    expect(tree[0].key).toBe("region:CA1");
    expect([tree[0].sessionCount, tree[0].regionCount]).toEqual([3, 1]);
    expect(groupCountLabel(tree[0])).toBe("3 sessions");
  });
});

describe("helpers", () => {
  it("handles an empty list and does not mutate the input", () => {
    for (const by of ["subject", "session", "region"] as const) expect(groupItems([], by)).toEqual([]);
    const before = keys(ITEMS);
    groupItems(ITEMS, "region");
    expect(keys(ITEMS)).toEqual(before);
  });

  it("keeps extra fields on the items", () => {
    const withSplit = ITEMS.map((i) => ({ ...i, split: { seed: 1 } }));
    expect(groupItems(withSplit, "session")[0].items[0].split).toEqual({ seed: 1 });
  });

  it("summarises a selection", () => {
    expect(selectionSummary(ITEMS)).toBe("5 items in 3 sessions");
    expect(selectionSummary([ITEMS[0]])).toBe("1 item in 1 session");
  });
});
