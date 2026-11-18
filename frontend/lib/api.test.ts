import { describe, expect, it } from "vitest";
import { ApiError, apiFetch, apiUrl, errorMessage, toQuery } from "@/lib/api";

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

describe("errorMessage", () => {
  it("hints at `make api` when the API is unreachable", () => {
    expect(errorMessage(new ApiError(0, null), "x")).toMatch(/Cannot reach the API.*make api/);
  });
  it("uses the API's detail string, message or validation messages", () => {
    expect(errorMessage(new ApiError(503, { detail: "Database down" }), "x")).toBe("Database down");
    expect(errorMessage(new ApiError(422, { detail: { message: "Not in catalog" } }), "x")).toBe(
      "Not in catalog",
    );
    expect(
      errorMessage(new ApiError(422, { detail: [{ msg: "too big" }, { msg: "too small" }] }), "x"),
    ).toBe("too big. too small");
  });
  it("falls back with the status, or for non-API errors", () => {
    expect(errorMessage(new ApiError(500, "Internal Server Error"), "Could not load")).toBe(
      "Could not load (HTTP 500)",
    );
    expect(errorMessage(new Error("boom"), "Could not load")).toBe("Could not load");
  });
});

describe("apiFetch", () => {
  it("turns a network failure into ApiError status 0", async () => {
    const realFetch = globalThis.fetch;
    globalThis.fetch = () => Promise.reject(new TypeError("Failed to fetch"));
    try {
      await expect(apiFetch("/api/health")).rejects.toMatchObject({ status: 0 });
    } finally {
      globalThis.fetch = realFetch;
    }
  });
  it("keeps a non-JSON error body as text", async () => {
    const realFetch = globalThis.fetch;
    globalThis.fetch = () => Promise.resolve(new Response("Internal Server Error", { status: 500 }));
    try {
      await expect(apiFetch("/api/health")).rejects.toMatchObject({
        status: 500,
        body: "Internal Server Error",
      });
    } finally {
      globalThis.fetch = realFetch;
    }
  });
});
