/** A worker counts as online when its newest heartbeat is under this age. */
export const WORKER_ONLINE_MS = 15_000;

export function isWorkerOnline(lastSeen: string | null | undefined, now = Date.now()): boolean {
  if (!lastSeen) return false;
  const seen = Date.parse(lastSeen);
  return Number.isFinite(seen) && now - seen < WORKER_ONLINE_MS;
}
