import { afterEach, expect, it, vi } from "vitest";
import { consumeStream, streamFetch } from "./stream";

afterEach(() => vi.unstubAllGlobals());
it("preserves HTTP Problems for the generated stream client", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: 401,
          code: 401,
          title: "未登录",
          detail: "请登录",
          message: "请登录",
          error_key: "UNAUTHORIZED",
        }),
        { status: 401 },
      ),
    ),
  );
  await expect(streamFetch("http://localhost")).rejects.toMatchObject({
    status: 401,
    errorKey: "UNAUTHORIZED",
  });
});
it("rejects JSON posing as a successful stream", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(new Response("{}", { headers: { "content-type": "application/json" } })),
  );
  await expect(streamFetch("http://localhost")).rejects.toMatchObject({
    errorKey: "API_CONTRACT_MISMATCH",
  });
});
it("requires a terminal event and forwards swallowed transport errors", async () => {
  const signal = new AbortController().signal;
  await expect(
    consumeStream(
      async () => ({
        stream: (async function* () {
          yield "partial";
        })(),
      }),
      () => false,
      signal,
    ),
  ).rejects.toMatchObject({ errorKey: "ANSWER_STREAM_INTERRUPTED" });
  await expect(
    consumeStream(
      async (fail) => ({
        stream: (async function* () {
          fail(new TypeError("network"));
          yield "partial";
        })(),
      }),
      () => false,
      signal,
    ),
  ).rejects.toMatchObject({ errorKey: "NETWORK_ERROR" });
});
it("ends only on a terminal event and ignores cancelled events", async () => {
  const receive = vi.fn((value: string) => value === "done");
  await consumeStream(
    async () => ({
      stream: (async function* () {
        yield "delta";
        yield "done";
        yield "late";
      })(),
    }),
    receive,
    new AbortController().signal,
  );
  expect(receive.mock.calls).toEqual([["delta"], ["done"]]);
  const abort = new AbortController();
  abort.abort();
  await expect(
    consumeStream(
      async () => ({
        stream: (async function* () {
          yield "late";
        })(),
      }),
      receive,
      abort.signal,
    ),
  ).rejects.toMatchObject({ name: "AbortError" });
});
