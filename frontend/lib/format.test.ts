import { describe, expect, it } from "vitest";
import { experimentMeta, formatDate, itemsAndRuns, plural } from "@/lib/format";

describe("formatDate", () => {
  it("formats like Nov 4, 2026", () => {
    // Midday UTC, so the local date is Nov 4 in every time zone from UTC-11 to UTC+11.
    expect(formatDate("2026-11-04T12:00:00+00:00")).toBe("Nov 4, 2026");
    expect(formatDate("2026-01-15T12:00:00Z")).toBe("Jan 15, 2026");
  });
});

describe("counts", () => {
  it("pluralises", () => {
    expect(plural(0, "run")).toBe("0 runs");
    expect(plural(1, "run")).toBe("1 run");
    expect(plural(2, "run")).toBe("2 runs");
  });

  it("builds the list and header lines", () => {
    const e = {
      created_at: "2026-11-04T12:00:00Z",
      item_count: 6,
      session_count: 3,
      run_count: 1,
    };
    expect(itemsAndRuns(e)).toBe("6 items · 1 run");
    expect(experimentMeta(e)).toBe("Created Nov 4, 2026 · 6 items in 3 sessions · 1 run");
  });
});
