import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AnswerContent } from "./answer-content";

afterEach(cleanup);
describe("答案安全呈现", () => {
  it("renders untrusted HTML and links as text", () => {
    const content =
      "<script>alert(1)</script> <img src=x onerror=alert(1)> [link](javascript:alert(1))";
    const { container } = render(<AnswerContent content={content} />);
    expect(container.textContent).toBe(content);
    expect(container.querySelector("script, img, a")).toBeNull();
  });
  it("preserves multiline code and supports emphasis without interpreting markup", () => {
    const { container } = render(
      <AnswerContent
        content={"**重点**\n\n```html\n<div>safe</div>\nline 2\n```\n\n使用 `code`。"}
      />,
    );
    expect(screen.getByText("重点").tagName).toBe("STRONG");
    expect(container.querySelector("pre code")?.textContent).toBe("<div>safe</div>\nline 2\n");
    expect(screen.getByText("code").tagName).toBe("CODE");
  });
});
