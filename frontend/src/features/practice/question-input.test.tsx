import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QuestionInput } from "./question-input";
import { baseQuestion, singleQuestion } from "./fixtures.test-support";
afterEach(cleanup);
describe("五种真实答案类型", () => {
  it("单选传稳定选项ID，显示阳光黄选中态", () => {
    const change = vi.fn();
    render(
      <QuestionInput
        question={singleQuestion}
        value={{ type: "single_choice", option_id: "B" }}
        onChange={change}
        disabled={false}
      />,
    );
    expect(screen.getByRole("radio", { name: "B · 独立事务" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "B · 独立事务" }).closest("label")).toHaveClass(
      "bg-muted",
    );
    fireEvent.click(screen.getByRole("radio", { name: "A · 加入事务" }));
    expect(change).toHaveBeenCalledWith({ type: "single_choice", option_id: "A" });
  });
  it("多选更新选项集合，取消选项保留其他选项", () => {
    const change = vi.fn();
    render(
      <QuestionInput
        question={{ ...singleQuestion, type: "multiple_choice", answer: ["A", "B"] }}
        value={{ type: "multiple_choice", option_ids: ["A"] }}
        onChange={change}
        disabled={false}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "B · 独立事务" }));
    expect(change).toHaveBeenLastCalledWith({ type: "multiple_choice", option_ids: ["A", "B"] });
    fireEvent.click(screen.getByRole("checkbox", { name: "A · 加入事务" }));
    expect(change).toHaveBeenLastCalledWith({ type: "multiple_choice", option_ids: [] });
  });
  it("判断题正确保存 false 而不是字符串", () => {
    const change = vi.fn();
    render(
      <QuestionInput
        question={{ ...baseQuestion, type: "true_false", answer: false }}
        onChange={change}
        disabled={false}
      />,
    );
    fireEvent.click(screen.getByRole("radio", { name: "错误" }));
    expect(change).toHaveBeenCalledWith({ type: "true_false", value: false });
  });
  it.each(["short_answer", "code_text"] as const)("%s 保留原文且只发送文本", (type) => {
    const change = vi.fn();
    render(
      <QuestionInput
        question={{ ...baseQuestion, type, answer: ["边界"] }}
        onChange={change}
        disabled={false}
      />,
    );
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "  合成原文\nprint('x')  " },
    });
    expect(change).toHaveBeenCalledWith({ type, text: "  合成原文\nprint('x')  " });
    if (type === "code_text")
      expect(screen.getByText("仅评价代码文本，不执行代码")).toBeInTheDocument();
  });
});
