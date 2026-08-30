import { describe, expect, it } from "vitest";

import { validateAvatarFile } from "./upload";

describe("头像文件前置校验", () => {
  it("接受 JPEG、PNG 与 WebP", () => {
    expect(() =>
      validateAvatarFile(new File(["image"], "avatar.png", { type: "image/png" })),
    ).not.toThrow();
  });

  it("拒绝不支持的类型", () => {
    try {
      validateAvatarFile(new File(["gif"], "avatar.gif", { type: "image/gif" }));
      expect.unreachable("应拒绝 GIF");
    } catch (error) {
      expect(error).toMatchObject({ errorKey: "AVATAR_TYPE_INVALID" });
    }
  });

  it("拒绝超过 5 MB 的文件", () => {
    const file = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "large.webp", {
      type: "image/webp",
    });
    try {
      validateAvatarFile(file);
      expect.unreachable("应拒绝超大文件");
    } catch (error) {
      expect(error).toMatchObject({ errorKey: "AVATAR_TOO_LARGE" });
    }
  });
});
