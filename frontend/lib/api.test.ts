import { describe, expect, it } from "vitest";
import { apiUrl } from "@/lib/api";

describe("apiUrl", () => {
  it("joins the base URL and path with exactly one slash", () => {
    expect(apiUrl("/api/health")).toMatch(/[^/]\/api\/health$/);
    expect(apiUrl("api/health")).toBe(apiUrl("/api/health"));
  });
});
