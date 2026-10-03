/** Only lookup metadata is persisted; answers, sources and model content stay on the server. */
export type PendingPracticeRequest = {
  requestKey: string;
  operation: string;
  targetId: string;
  runId?: string;
};

function storageKey(owner: string, setId: string) {
  return `practice-request:v1:${encodeURIComponent(owner)}:${encodeURIComponent(setId)}`;
}

export function readPendingRequest(
  storage: Pick<Storage, "getItem">,
  owner: string,
  setId: string,
): PendingPracticeRequest | null {
  try {
    const raw = storage.getItem(storageKey(owner, setId));
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null) return null;
    const record = value as Record<string, unknown>;
    if (
      record.version !== 1 ||
      typeof record.requestKey !== "string" ||
      typeof record.operation !== "string" ||
      typeof record.targetId !== "string" ||
      (record.runId !== undefined && typeof record.runId !== "string")
    )
      return null;
    return {
      requestKey: record.requestKey,
      operation: record.operation,
      targetId: record.targetId,
      ...(typeof record.runId === "string" ? { runId: record.runId } : {}),
    };
  } catch {
    return null;
  }
}

export function writePendingRequest(
  storage: Pick<Storage, "setItem" | "removeItem">,
  owner: string,
  setId: string,
  value: PendingPracticeRequest | null,
): boolean {
  try {
    const key = storageKey(owner, setId);
    if (value) {
      storage.setItem(
        key,
        JSON.stringify({
          version: 1,
          requestKey: value.requestKey,
          operation: value.operation,
          targetId: value.targetId,
          ...(value.runId ? { runId: value.runId } : {}),
        }),
      );
    } else storage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}
