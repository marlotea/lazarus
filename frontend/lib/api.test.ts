import { describe, expect, it } from "vitest";
import { apiUrl, toQuery } from "@/lib/api";

describe("apiUrl", () => {
  it("joins the base URL and path with exactly one slash", () => {
    expect(apiUrl("/api/health")).toMatch(/[^/]\/api\/health$/);
    expect(apiUrl("api/health")).toBe(apiUrl("/api/health"));
  });
});

describe("toQuery", () => {
  it("repeats array keys and drops empty values", () => {
    expect(toQuery({ region: ["CA1", "DG"], subject: "", lab: undefined, min_units: 0 })).toBe(
      "?region=CA1&region=DG&min_units=0",
    );
    expect(toQuery({})).toBe("");
  });
});
