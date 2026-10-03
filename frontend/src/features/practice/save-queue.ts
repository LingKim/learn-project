/** Serialize answer writes. A failed write blocks subsequent saves until explicit recovery. */
export function createSaveQueue<Input, Result>(write: (input: Input) => Promise<Result>) {
  let tail: Promise<void> = Promise.resolve();
  let blocked: unknown;
  let hasFailure = false;
  let pending = 0;

  return {
    enqueue(input: Input): Promise<Result> {
      pending += 1;
      const result = tail.then(async () => {
        if (hasFailure) throw blocked;
        try {
          return await write(input);
        } catch (error) {
          hasFailure = true;
          blocked = error;
          throw error;
        }
      });
      tail = result.then(
        () => {
          pending -= 1;
        },
        () => {
          pending -= 1;
        },
      );
      return result;
    },
    async flush() {
      // 等待时仍可能有自动保存入队；尾指针稳定后才允许提交使用已确认版本。
      let observed: Promise<void>;
      do {
        observed = tail;
        await observed;
      } while (observed !== tail);
      if (hasFailure) throw blocked;
    },
    recover() {
      if (pending !== 0) throw new Error("请等待保存队列结束后恢复");
      hasFailure = false;
      blocked = undefined;
    },
  };
}
