import { beforeEach, describe, expect, it } from "vitest";
import { readPendingRequest, writePendingRequest } from "./request-recovery";

beforeEach(() => sessionStorage.clear());
describe("异步请求响应丢失恢复", () => {
  it("仅按账号和题集保存寻址元数据，刷新后恢复同 key 而不自动再次调用模型", () => {
    const ref = { requestKey: "uuid", operation: "plan", targetId: "set" };
    expect(writePendingRequest(sessionStorage, "alice", "set", ref)).toBe(true);
    expect(readPendingRequest(sessionStorage, "alice", "set")).toEqual(ref);
    expect(readPendingRequest(sessionStorage, "bob", "set")).toBeNull();
    expect(readPendingRequest(sessionStorage, "alice", "another")).toBeNull();
    writePendingRequest(sessionStorage, "alice", "set", null);
    expect(readPendingRequest(sessionStorage, "alice", "set")).toBeNull();
  });
  it("不持久化额外业务字段，忽略损坏数据和受限浏览器存储", () => {
    const ref = { requestKey: "uuid", operation: "submit", targetId: "attempt", answer: "private" };
    writePendingRequest(sessionStorage, "alice", "set", ref);
    expect(sessionStorage.getItem(sessionStorage.key(0)!)).not.toContain("private");
    expect(readPendingRequest({ getItem: () => "invalid json" }, "alice", "set")).toBeNull();
    expect(readPendingRequest({ getItem: () => '{"version":2}' }, "alice", "set")).toBeNull();
    expect(
      writePendingRequest(
        {
          setItem: () => {
            throw new Error("blocked");
          },
          removeItem: () => {},
        },
        "alice",
        "set",
        ref,
      ),
    ).toBe(false);
  });
});
