import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AnswerContent } from "./answer-content";

afterEach(cleanup);
describe("答案 Markdown 与媒体呈现", () => {
  it("renders GFM headings, lists, tasks, tables and emphasis", () => {
    const { container } = render(
      <AnswerContent
        content={
          "# 标题\n\n**重点** 与 ~~删除~~\n\n- 条目\n- [x] 完成\n\n> 引用\n\n| 名称 | 内容 |\n| --- | --- |\n| A | B |"
        }
      />,
    );
    expect(screen.getByRole("heading", { name: "标题" })).toBeTruthy();
    expect(screen.getByText("重点").tagName).toBe("STRONG");
    expect(screen.getByRole("checkbox")).toBeChecked();
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(container.querySelector("blockquote")?.textContent).toContain("引用");
    expect(screen.getByRole("table")).toHaveTextContent("名称内容AB");
    expect(container.querySelector("del")?.textContent).toBe("删除");
  });
  it("preserves code and renders unfinished streaming fences", () => {
    const { container, rerender } = render(
      <AnswerContent content={"```html\n<div>safe</div>\nline 2\n```\n\n使用 `code`。"} />,
    );
    expect(container.querySelector("pre code")?.textContent).toBe("<div>safe</div>\nline 2\n");
    expect(screen.getByText("code").tagName).toBe("CODE");
    rerender(<AnswerContent content={"```js\nconst a = 1;\n"} />);
    expect(container.querySelector("pre code")?.textContent).toBe("const a = 1;\n");
  });
  it("strips scripts, event handlers, iframes and unsafe URLs", () => {
    const { container } = render(
      <AnswerContent
        content={
          '<script>alert(1)</script><iframe src="https://evil.example"></iframe><img src="https://example.com/x.png" onerror="alert(1)"><video src="javascript:alert(1)" autoplay onerror="alert(1)"></video>\n\n[x](javascript:alert(1)) ![data](data:image/svg+xml;base64,eA==) [file](file:///tmp/x)'
        }
      />,
    );
    expect(container.querySelector("script,iframe,[onerror], [autoplay]")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("video")).toBeNull();
    expect(container.querySelector("img")?.getAttribute("src")).toBe("https://example.com/x.png");
  });
  it("opens image preview with a keyboard-accessible trigger and supports close", () => {
    render(<AnswerContent content="![示意图](/images/demo.png)" />);
    const trigger = screen.getByRole("button", { name: "放大图片：示意图" });
    expect(trigger.tagName).toBe("BUTTON");
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("img")).toHaveAttribute("src", "/images/demo.png");
    fireEvent.click(within(dialog).getByRole("button", { name: "关闭" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("shows image and player failures instead of broken silent resources", () => {
    const { container } = render(
      <AnswerContent content="![插图](https://example.com/image.png)\n\n[音频](https://example.com/voice.mp3)" />,
    );
    fireEvent.error(screen.getByRole("img"));
    fireEvent.error(container.querySelector("audio")!);
    expect(screen.getByText("图片无法加载：插图")).toBeTruthy();
    expect(screen.getByText(/音频无法加载/)).toBeTruthy();
  });
  it("recovers a failed partial media URL when the stream replaces it", () => {
    const { rerender } = render(<AnswerContent content="![插图](/partial.png)" />);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByText("图片无法加载：插图")).toBeTruthy();
    rerender(<AnswerContent content="![插图](/complete.png)" />);
    expect(screen.getByRole("img")).toHaveAttribute("src", "/complete.png");
  });
  it("uses safe native audio/video controls and sanitized sources without autoplay", () => {
    const { container } = render(
      <AnswerContent
        content={
          '<video autoplay poster="javascript:x" onplay="alert(1)"><source src="https://example.com/demo.mp4" type="video/mp4"><source src="data:video/mp4,evil"></video>\n\n<audio src="/voice.ogg" autoplay></audio>\n\n[视频](https://example.com/movie.webm?x=1)\n\n[官网](https://example.com)'
        }
      />,
    );
    expect(container.querySelectorAll("video")).toHaveLength(2);
    expect(container.querySelectorAll("source")).toHaveLength(1);
    for (const player of container.querySelectorAll("video,audio")) {
      expect(player).toHaveAttribute("controls");
      expect(player).toHaveAttribute("preload", "none");
      expect(player).not.toHaveAttribute("crossorigin");
      expect(player).not.toHaveAttribute("autoplay");
    }
    expect(screen.getByRole("link", { name: "官网" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    expect(screen.getByRole("link", { name: "官网" })).toHaveAttribute("target", "_blank");
  });
});
