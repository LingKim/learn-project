/** Persist lookup metadata only, scoped to the owner and target; never store learning content. */
function storageKey(owner: string, targetId: string) {
  return `knowledge-request:v1:${encodeURIComponent(owner)}:${encodeURIComponent(targetId || "new")}`;
}
export function readKnowledgeRequest(
  storage: Pick<Storage, "getItem">,
  owner: string,
  targetId: string,
) {
  if (!owner) return "";
  try {
    const value = storage.getItem(storageKey(owner, targetId));
    return value && /^[0-9a-f-]{36}$/i.test(value) ? value : "";
  } catch {
    return "";
  }
}
export function writeKnowledgeRequest(
  storage: Pick<Storage, "setItem" | "removeItem">,
  owner: string,
  targetId: string,
  requestKey: string,
) {
  if (!owner) return;
  try {
    if (requestKey) storage.setItem(storageKey(owner, targetId), requestKey);
    else storage.removeItem(storageKey(owner, targetId));
  } catch {
    /* Task URLs and explicit lookup remain available. */
  }
}
