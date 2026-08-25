import { describe, expect, it } from "vitest";

import { requestMutation, requestNoContent, requestPageData, requestQueryData } from "./protocol";

function success<T>(data: T, status = 200) {
  return Promise.resolve({
    data,
    response: new Response(null, { status }),
  });
}

describe("API protocol adapters", () => {
  it("unwraps query data", async () => {
    const data = await requestQueryData<{ id: number }>(() =>
      success({ code: 200, message: "查询成功", data: { id: 1 } }),
    );

    expect(data).toEqual({ id: 1 });
  });

  it("rejects mismatched HTTP and body status codes", async () => {
    await expect(
      requestQueryData(() => success({ code: 201, message: "查询成功", data: {} })),
    ).rejects.toMatchObject({
      errorKey: "API_CONTRACT_MISMATCH",
      status: 200,
    });
  });

  it("returns page data with metadata", async () => {
    const page = await requestPageData<{ id: number }>(() =>
      success({
        code: 200,
        message: "查询成功",
        data: [{ id: 1 }],
        meta: { page: 1, page_size: 20, total: 1, total_pages: 1 },
      }),
    );

    expect(page).toEqual({
      data: [{ id: 1 }],
      meta: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
  });

  it("keeps the backend message for mutations", async () => {
    const result = await requestMutation<{ id: number }>(() =>
      success({ code: 201, message: "创建成功", data: { id: 1 } }, 201),
    );

    expect(result).toEqual({ data: { id: 1 }, message: "创建成功" });
  });

  it("supports 204 with a caller-provided message", async () => {
    const result = await requestNoContent(() => success({}, 204), "删除成功");

    expect(result).toEqual({ data: undefined, message: "删除成功" });
  });
});
