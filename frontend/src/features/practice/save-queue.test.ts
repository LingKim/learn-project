import { describe, expect, it, vi } from "vitest";
import { createSaveQueue } from "./save-queue";

describe("练习答案保存队列", () => {
  it("flush期间新加入的保存也必须完成，才能越过提交屏障", async () => {
    let finishFirst!: (value: string) => void;
    let finishSecond!: (value: string) => void;
    const queue = createSaveQueue(
      (value: string) =>
        new Promise<string>((resolve) => {
          if (value === "first") finishFirst = resolve;
          else finishSecond = resolve;
        }),
    );
    const first = queue.enqueue("first");
    const flushed = vi.fn();
    const flushing = queue.flush().then(flushed);
    await Promise.resolve();
    const second = queue.enqueue("second");
    finishFirst("saved first");
    await first;
    await Promise.resolve();
    await Promise.resolve();
    expect(flushed).not.toHaveBeenCalled();
    finishSecond("saved second");
    await second;
    await flushing;
    expect(flushed).toHaveBeenCalledTimes(1);
  });
  it("前次服务器保存确认后才发送后次输入，并使用新的版本", async () => {
    let finish: (value: number) => void = () => {};
    let version = 1;
    const write = vi.fn((text: string) => {
      const current = version;
      if (text === "old")
        return new Promise<number>((resolve) => {
          finish = (value) => {
            version = value;
            resolve(value);
          };
        });
      return Promise.resolve(current + 1);
    });
    const queue = createSaveQueue(write);
    const first = queue.enqueue("old");
    const second = queue.enqueue("new");
    await Promise.resolve();
    expect(write).toHaveBeenCalledTimes(1);
    finish(2);
    await expect(first).resolves.toBe(2);
    await expect(second).resolves.toBe(3);
    expect(write.mock.calls.map(([value]) => value)).toEqual(["old", "new"]);
    await queue.flush();
  });

  it("保存冲突停止后续写入，提交前 flush 失败，明确恢复后才继续", async () => {
    const conflict = new Error("version conflict");
    const write = vi.fn().mockRejectedValueOnce(conflict).mockResolvedValue("saved");
    const queue = createSaveQueue(write);
    const first = queue.enqueue("first");
    const second = queue.enqueue("second");
    await expect(first).rejects.toBe(conflict);
    await expect(second).rejects.toBe(conflict);
    await expect(queue.flush()).rejects.toBe(conflict);
    expect(write).toHaveBeenCalledTimes(1);
    queue.recover();
    await expect(queue.enqueue("kept local input")).resolves.toBe("saved");
  });
});
