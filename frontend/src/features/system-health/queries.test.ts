import { describe, expect, it } from "vitest";

import { systemHealthKeys, systemHealthQueryOptions } from "./queries";

describe("system health query options", () => {
  it("uses the feature key factory and keeps health retries disabled", () => {
    const options = systemHealthQueryOptions();

    expect(options.queryKey).toEqual(systemHealthKeys.readiness());
    expect(options.retry).toBe(false);
    expect(options.refetchInterval).toBe(30_000);
  });
});
