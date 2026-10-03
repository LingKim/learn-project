import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { AttemptPanel } from "./attempt-panel";
import * as api from "./api";
import { emptyAttempt, singleQuestion, textQuestion } from "./fixtures.test-support";
vi.mock("./api", () => ({
  savePracticeAnswer: vi.fn(),
  submitPracticeAnswer: vi.fn(),
  getPracticeAttempt: vi.fn(),
  getPracticeSource: vi.fn(),
  setPracticeFeedback: vi.fn(),
  completePractice: vi.fn(),
}));
function mount(attempt = emptyAttempt) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onRequest = vi.fn(async (_operation, _key, _target, action) => (await action()).data);
  const complete = vi.fn();
  const view = render(
    <QueryClientProvider client={client}>
      <AttemptPanel
        attempt={attempt}
        title="合成练习"
        busy={false}
        onRequest={onRequest}
        onRegrade={vi.fn()}
        onComplete={complete}
      />
    </QueryClientProvider>,
  );
  return { client, onRequest, complete, view };
}
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getPracticeAttempt).mockResolvedValue(emptyAttempt);
  vi.mocked(api.submitPracticeAnswer).mockResolvedValue({
    data: {
      submission_id: "sub",
      question_id: textQuestion.question_id,
      answer: { type: "short_answer", text: "合成回答" },
      answer_version: 1,
      grades: [],
    },
    message: "ok",
  });
});
describe("练习保存与提交边界", () => {
  it("提交等待保存时离开页面，已发保存可结束但不能继续提交或填旧缓存", async () => {
    let finish!: (value: Awaited<ReturnType<typeof api.savePracticeAnswer>>) => void;
    vi.mocked(api.savePracticeAnswer).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const { client, onRequest, view } = mount();
    fireEvent.change(screen.getByLabelText("简答答案"), { target: { value: "合成草稿" } });
    fireEvent.click(screen.getByRole("button", { name: "提交本题" }));
    await waitFor(() => expect(api.savePracticeAnswer).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText("简答答案"), { target: { value: "等待时的新草稿" } });
    view.unmount();
    await act(async () => {
      finish({
        data: {
          ...emptyAttempt,
          version: 2,
          answers: [
            {
              question_id: textQuestion.question_id,
              version: 1,
              answer: { type: "short_answer", text: "合成草稿" },
            },
          ],
        },
        message: "ok",
      });
    });
    expect(onRequest).not.toHaveBeenCalled();
    expect(api.submitPracticeAnswer).not.toHaveBeenCalled();
    expect(client.getQueryData(["practice", "attempts", "attempt"])).toBeUndefined();
  });
  it("完成请求发出后离开页面，迟到响应不能调用旧报告跳转", async () => {
    let finish!: (value: Awaited<ReturnType<typeof api.completePractice>>) => void;
    vi.mocked(api.completePractice).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const { client, complete, view } = mount();
    fireEvent.click(screen.getByRole("button", { name: "完成练习并查看报告" }));
    await waitFor(() => expect(api.completePractice).toHaveBeenCalled());
    view.unmount();
    await act(async () => {
      finish({ data: { ...emptyAttempt, status: "completed" }, message: "ok" });
    });
    expect(complete).not.toHaveBeenCalled();
    expect(client.getQueryData(["practice", "attempts", "attempt"])).toBeUndefined();
  });
  it("已提交文本题可以切到下一题，按真实版本保存当前位置", async () => {
    const nextQuestion = { ...singleQuestion, question_id: "22222222-2222-4222-8222-222222222222" };
    const attempt: api.AttemptView = {
      ...emptyAttempt,
      version: 3,
      questions: [textQuestion, nextQuestion],
      answers: [
        {
          question_id: textQuestion.question_id,
          version: 1,
          answer: { type: "short_answer", text: "已提交原文" },
        },
      ],
      submissions: [
        {
          submission_id: "sub",
          question_id: textQuestion.question_id,
          answer: { type: "short_answer", text: "已提交原文" },
          answer_version: 1,
          grades: [],
          run: null,
        },
      ],
    };
    vi.mocked(api.savePracticeAnswer).mockResolvedValue({
      data: { ...attempt, version: 4, current_question_id: nextQuestion.question_id },
      message: "ok",
    });
    mount(attempt);
    expect(screen.getByLabelText("简答答案")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "第2题" }));
    await screen.findByRole("heading", { name: "合成练习 · 第 2 题 / 共 2 题" });
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.getByRole("status", { name: "答案保存状态" })).toHaveTextContent("尚未填写");
    expect(api.savePracticeAnswer).toHaveBeenCalledWith(
      "attempt",
      textQuestion.question_id,
      expect.objectContaining({
        expected_version: 3,
        current_question_id: nextQuestion.question_id,
      }),
    );
  });
  it("完成后的历史题目切换不发出答案写入", async () => {
    mount({
      ...emptyAttempt,
      status: "completed",
      questions: [
        textQuestion,
        { ...singleQuestion, question_id: "22222222-2222-4222-8222-222222222222" },
      ],
      answers: [
        {
          question_id: textQuestion.question_id,
          version: 1,
          answer: { type: "short_answer", text: "历史原文" },
        },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: "第2题" }));
    await screen.findByRole("heading", { name: "合成练习 · 第 2 题 / 共 2 题" });
    expect(api.savePracticeAnswer).not.toHaveBeenCalled();
  });
  it("后台刷新其他页面的新版本不能覆盖未保存草稿或绕过保存冲突", async () => {
    vi.mocked(api.savePracticeAnswer).mockRejectedValueOnce(
      new ApiError("其他页面已更新", { status: 409, errorKey: "PRACTICE_VERSION_CONFLICT" }),
    );
    const { client, onRequest, complete, view } = mount();
    fireEvent.change(screen.getByLabelText("简答答案"), { target: { value: "本地未保存草稿" } });
    view.rerender(
      <QueryClientProvider client={client}>
        <AttemptPanel
          attempt={{
            ...emptyAttempt,
            version: 4,
            answers: [
              {
                question_id: textQuestion.question_id,
                version: 2,
                answer: { type: "short_answer", text: "其他页面的新答案" },
              },
            ],
          }}
          title="合成练习"
          busy={false}
          onRequest={onRequest}
          onRegrade={vi.fn()}
          onComplete={complete}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByLabelText("简答答案")).toHaveValue("本地未保存草稿");
    fireEvent.click(screen.getByRole("button", { name: "提交本题" }));
    await screen.findByText("其他页面已更新");
    expect(api.savePracticeAnswer).toHaveBeenCalledWith(
      "attempt",
      textQuestion.question_id,
      expect.objectContaining({
        expected_version: 1,
        answer: { type: "short_answer", text: "本地未保存草稿" },
      }),
    );
    expect(api.submitPracticeAnswer).not.toHaveBeenCalled();
  });
  it("未确认保存不显示已保存，提交等待保存并使用真实新版本", async () => {
    let finish!: (value: Awaited<ReturnType<typeof api.savePracticeAnswer>>) => void;
    vi.mocked(api.savePracticeAnswer).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    mount();
    fireEvent.change(screen.getByLabelText("简答答案"), { target: { value: "合成回答" } });
    expect(screen.getByRole("status", { name: "答案保存状态" })).toHaveTextContent("尚未保存");
    fireEvent.click(screen.getByRole("button", { name: "提交本题" }));
    await waitFor(() => expect(api.savePracticeAnswer).toHaveBeenCalledTimes(1));
    expect(api.submitPracticeAnswer).not.toHaveBeenCalled();
    const saved = {
      ...emptyAttempt,
      version: 2,
      answers: [
        {
          question_id: textQuestion.question_id,
          version: 1,
          answer: { type: "short_answer" as const, text: "合成回答" },
        },
      ],
    };
    await act(async () => {
      finish({ data: saved, message: "ok" });
    });
    await waitFor(() =>
      expect(api.submitPracticeAnswer).toHaveBeenCalledWith(
        "attempt",
        textQuestion.question_id,
        expect.objectContaining({ expected_version: 2, answer_version: 1 }),
      ),
    );
    expect(screen.getByRole("status", { name: "答案保存状态" })).toHaveTextContent("已保存");
  });
  it("提交等待保存期间的新输入必须保存后再提交，不能提交较旧答案", async () => {
    let finish!: (value: Awaited<ReturnType<typeof api.savePracticeAnswer>>) => void;
    vi.mocked(api.savePracticeAnswer)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      )
      .mockResolvedValue({
        data: {
          ...emptyAttempt,
          version: 3,
          answers: [
            {
              question_id: textQuestion.question_id,
              version: 2,
              answer: { type: "short_answer", text: "最终输入" },
            },
          ],
        },
        message: "ok",
      });
    mount();
    fireEvent.change(screen.getByLabelText("简答答案"), { target: { value: "较旧输入" } });
    fireEvent.click(screen.getByRole("button", { name: "提交本题" }));
    await waitFor(() => expect(api.savePracticeAnswer).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText("简答答案"), { target: { value: "最终输入" } });
    await act(async () => {
      finish({
        data: {
          ...emptyAttempt,
          version: 2,
          answers: [
            {
              question_id: textQuestion.question_id,
              version: 1,
              answer: { type: "short_answer", text: "较旧输入" },
            },
          ],
        },
        message: "ok",
      });
    });
    await waitFor(() => expect(api.submitPracticeAnswer).toHaveBeenCalled());
    expect(api.submitPracticeAnswer).toHaveBeenCalledWith(
      "attempt",
      textQuestion.question_id,
      expect.objectContaining({ expected_version: 3, answer_version: 2 }),
    );
    expect(api.savePracticeAnswer).toHaveBeenCalledTimes(2);
  });
  it("保存冲突保留本地答案并阻止提交，明确读取最新版本后再保存", async () => {
    vi.mocked(api.savePracticeAnswer).mockRejectedValueOnce(
      new ApiError("其他页面已更新", { status: 409, errorKey: "PRACTICE_VERSION_CONFLICT" }),
    );
    vi.mocked(api.getPracticeAttempt).mockResolvedValue({ ...emptyAttempt, version: 4 });
    vi.mocked(api.savePracticeAnswer).mockResolvedValue({
      data: {
        ...emptyAttempt,
        version: 5,
        answers: [
          {
            question_id: textQuestion.question_id,
            version: 1,
            answer: { type: "short_answer", text: "保留的本地原文" },
          },
        ],
      },
      message: "ok",
    });
    mount();
    fireEvent.change(screen.getByLabelText("简答答案"), { target: { value: "保留的本地原文" } });
    fireEvent.click(screen.getByRole("button", { name: "提交本题" }));
    await screen.findByText("其他页面已更新");
    expect(screen.getByLabelText("简答答案")).toHaveValue("保留的本地原文");
    expect(api.submitPracticeAnswer).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "读取最新答案" }));
    await waitFor(() => expect(api.getPracticeAttempt).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText("其他页面已更新")).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "保存答案" }));
    await waitFor(() => expect(api.savePracticeAnswer).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.savePracticeAnswer).mock.calls[1][2]).toMatchObject({
      expected_version: 4,
      answer: { type: "short_answer", text: "保留的本地原文" },
    });
  });
  it("刷新挂载恢复服务端已保存原文，completed尝试不能继续写答案", () => {
    mount({
      ...emptyAttempt,
      status: "completed",
      answers: [
        {
          question_id: textQuestion.question_id,
          version: 2,
          answer: { type: "short_answer", text: "服务器已确认保存" },
        },
      ],
    });
    expect(screen.getByLabelText("简答答案")).toHaveValue("服务器已确认保存");
    expect(screen.getByLabelText("简答答案")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "提交本题" })).not.toBeInTheDocument();
  });
});
