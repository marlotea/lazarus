import { describe, expect, it } from "vitest";
import { isWorkerOnline } from "@/lib/worker";

describe("isWorkerOnline", () => {
  const now = Date.parse("2026-11-18T12:00:00Z");

  it("is online when the heartbeat is under 15 s old", () => {
    expect(isWorkerOnline("2026-11-18T11:59:50Z", now)).toBe(true);
  });

  it("is offline when the heartbeat is stale or missing", () => {
    expect(isWorkerOnline("2026-11-18T11:59:44Z", now)).toBe(false);
    expect(isWorkerOnline(null, now)).toBe(false);
    expect(isWorkerOnline(undefined, now)).toBe(false);
  });
});
