"use client";

import Link from "next/link";
import { PracticeModes } from "./practice-layout";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AnswerContent } from "@/features/learning/answer-content";
import type {
  AttemptView,
  PracticeAnswer,
  SubmitRequest,
  GradeView,
  RunView,
  SubmissionGradeView,
} from "./api";
import type { MutationResult } from "@/lib/api/protocol";
import {
  practiceAttemptOptions,
  practiceKeys,
  saveAnswerOptions,
  submitAnswerOptions,
  completePracticeOptions,
  isActiveRun,
} from "./queries";
import { createSaveQueue } from "./save-queue";
import { useActiveContext } from "./use-active-context";
import { QuestionInput } from "./question-input";
import { GradePanel, FeedbackButtons, answerText } from "./grade-panel";
import { SourceLinks } from "./source-links";
import { difficultyLabels, questionLabels } from "./config-form";
import { cn } from "@/lib/utils";

export type StartPracticeRun = (
  operation: RunView["operation"],
  key: string,
  targetId: string,
  action: () => Promise<MutationResult<RunView | SubmissionGradeView>>,
) => Promise<RunView | SubmissionGradeView>;
export function AttemptPanel({
  attempt,
  title,
  busy,
  resultGrade,
  onRequest,
  onRegrade,
  onComplete,
}: {
  attempt: AttemptView;
  title: string;
  busy: boolean;
  resultGrade?: GradeView;
  onRequest: StartPracticeRun;
  onRegrade: (id: string, reason: string) => Promise<void>;
  onComplete: () => void;
}) {
  const isCurrent = useActiveContext(attempt.id);
  const client = useQueryClient();
  const save = useMutation(saveAnswerOptions());
  const submit = useMutation(submitAnswerOptions());
  const complete = useMutation(completePracticeOptions());
  const saved = useRef(attempt);
  const [drafts, setDrafts] = useState<Record<string, PracticeAnswer>>(() =>
    Object.fromEntries(attempt.answers.map((a) => [a.question_id, a.answer])),
  );
  const draftRef = useRef(drafts);
  const dirty = useRef(new Set<string>());
  const [current, setCurrent] = useState(
    attempt.current_question_id ?? attempt.questions[0]?.question_id ?? "",
  );
  const [status, setStatusState] = useState(() =>
    attempt.answers.some(
      (a) => a.question_id === (attempt.current_question_id ?? attempt.questions[0]?.question_id),
    )
      ? "已保存"
      : "尚未填写",
  );
  const [error, setErrorState] = useState<string | null>(null);
  function setStatus(value: string) {
    if (isCurrent()) setStatusState(value);
  }
  function setError(value: string | null) {
    if (isCurrent()) setErrorState(value);
  }
  const [selectedSubmission, setSelectedSubmission] = useState("");
  const [selectedGrade, setSelectedGrade] = useState("");
  const [editing, setEditing] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduled = useRef<{
    questionId: string;
    answer: PracticeAnswer;
    currentId: string;
  } | null>(null);
  const [queue] = useState(() =>
    createSaveQueue(
      async (input: { questionId: string; answer: PracticeAnswer; currentId: string }) => {
        if (!isCurrent()) throw new Error("练习页面已切换");
        const result = await save.mutateAsync({
          id: attempt.id,
          questionId: input.questionId,
          body: {
            expected_version: saved.current.version,
            answer: input.answer,
            current_question_id: input.currentId,
          },
        });
        if (!isCurrent()) return result.data;
        saved.current = result.data;
        client.setQueryData(practiceKeys.attempt(attempt.id), result.data);
        if (
          !scheduled.current &&
          JSON.stringify(draftRef.current[input.questionId]) === JSON.stringify(input.answer)
        ) {
          dirty.current.delete(input.questionId);
          setStatus("已保存");
        }
        return result.data;
      },
    ),
  );
  useEffect(() => {
    if (attempt.version > saved.current.version && dirty.current.size === 0) {
      saved.current = attempt;
      const restored = Object.fromEntries(attempt.answers.map((a) => [a.question_id, a.answer]));
      draftRef.current = restored;
      setDrafts(restored);
    }
  }, [attempt]);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  async function saveScheduled() {
    if (!isCurrent()) return;
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    const input = scheduled.current;
    scheduled.current = null;
    if (!input) return;
    setStatus("正在保存…");
    try {
      await queue.enqueue(input);
      setError(null);
    } catch (e) {
      setStatus("保存失败，输入已保留");
      setError(e instanceof Error ? e.message : "保存未完成");
      throw e;
    }
  }
  function change(answer: PracticeAnswer) {
    if (!isCurrent()) return;
    dirty.current.add(current);
    const next = { ...draftRef.current, [current]: answer };
    draftRef.current = next;
    setDrafts(next);
    setStatus("尚未保存");
    scheduled.current = { questionId: current, answer, currentId: current };
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      void saveScheduled().catch(() => {});
    }, 500);
  }
  async function flush() {
    // 提交和切题必须等到等待期间产生的新草稿也保存，才能使用服务器确认的答案版本。
    do {
      if (!isCurrent()) return;
      await saveScheduled();
      if (!isCurrent()) return;
      await queue.flush();
      if (!isCurrent()) return;
    } while (scheduled.current);
  }
  async function navigate(id: string) {
    try {
      await flush();
      if (!isCurrent()) return;
      const value = draftRef.current[current];
      if (value && id !== current && attempt.status !== "completed") {
        await queue.enqueue({ questionId: current, answer: value, currentId: id });
        if (!isCurrent()) return;
      }
      setCurrent(id);
      setStatus(saved.current.answers.some((a) => a.question_id === id) ? "已保存" : "尚未填写");
      setSelectedSubmission("");
      setSelectedGrade("");
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "切换题目未完成，输入已保留");
    }
  }
  async function recover() {
    try {
      await queue.flush();
    } catch {
      /* Recovery is explicit and keeps local drafts. */
    }
    try {
      if (!isCurrent()) return;
      const fresh = await client.fetchQuery(practiceAttemptOptions(attempt.id));
      if (!isCurrent()) return;
      saved.current = fresh;
      queue.recover();
      setError(null);
      setStatus("已读取最新版本，当前输入保留，尚未保存");
      const value = draftRef.current[current];
      if (value) scheduled.current = { questionId: current, answer: value, currentId: current };
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取最新答案失败");
    }
  }
  async function send() {
    try {
      await flush();
      if (!isCurrent()) return;
      const answer = saved.current.answers.find((a) => a.question_id === current);
      if (!answer) {
        setError("请先填写并保存答案。");
        return;
      }
      const body: SubmitRequest = {
        expected_version: saved.current.version,
        answer_version: answer.version,
        request_key: crypto.randomUUID(),
      };
      await onRequest("grade", body.request_key, attempt.id, () =>
        submit.mutateAsync({ id: attempt.id, questionId: current, body }),
      );
      if (!isCurrent()) return;
      setEditing(false);
      setSelectedSubmission("");
      setSelectedGrade("");
      await client.invalidateQueries({ queryKey: practiceKeys.attempt(attempt.id) });
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交未完成，答案已保留");
    }
  }
  async function finish() {
    try {
      await flush();
      if (!isCurrent()) return;
      const result = await complete.mutateAsync({ id: attempt.id, version: saved.current.version });
      if (!isCurrent()) return;
      saved.current = result.data;
      client.setQueryData(practiceKeys.attempt(attempt.id), result.data);
      onComplete();
    } catch (e) {
      setError(e instanceof Error ? e.message : "完成请求未成功");
    }
  }
  const question = attempt.questions.find((q) => q.question_id === current) ?? attempt.questions[0];
  if (!question) return <p className="py-6 text-sm">题集为空，请回预览生成题目。</p>;
  const index = attempt.questions.findIndex((q) => q.question_id === question.question_id);
  const submissions = attempt.submissions.filter((s) => s.question_id === question.question_id);
  const latest = submissions.at(-1);
  const shown = submissions.find((s) => s.submission_id === selectedSubmission) ?? latest;
  const matchingRunGrade =
    resultGrade?.submission_id === shown?.submission_id ? resultGrade : undefined;
  const grade =
    shown?.grades.find((g) => g.id === selectedGrade) ?? matchingRunGrade ?? shown?.grades.at(-1);
  const grading = isActiveRun(shown?.run);
  const locked =
    attempt.status === "completed" ||
    busy ||
    submit.isPending ||
    complete.isPending ||
    (!editing && Boolean(latest));
  const subjective = question.type === "short_answer" || question.type === "code_text";
  const full = question.rubric.every((d) => d.max_score != null)
    ? question.rubric.reduce((sum, d) => sum + (d.max_score ?? 0), 0)
    : null;
  return (
    <div className="min-w-0">
      <header className="flex min-h-[62px] flex-wrap items-center justify-between gap-3 border-y border-border bg-surface px-4 py-3">
        <div>
          <h2 className="text-base font-semibold">
            {title} · 第 {index + 1} 题 / 共 {attempt.questions.length} 题
          </h2>
          <p role="status" aria-label="答案保存状态" className="mt-1 text-xs text-muted-foreground">
            {status}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={
            busy ||
            complete.isPending ||
            attempt.status === "completed" ||
            attempt.submissions.some((s) => isActiveRun(s.run))
          }
          onClick={() => {
            void finish();
          }}
        >
          完成练习并查看报告
        </Button>
      </header>
      <div className="border-b border-border px-4 py-1.5 lg:px-20 xl:px-48">
        <PracticeModes />
      </div>
      <div className="px-4 py-2">
        <Link
          href={`/learning/practice/${attempt.set_id}`}
          className="text-xs text-muted-foreground underline"
        >
          返回练习历史
        </Link>
      </div>
      <div className="flex min-w-0 flex-col lg:flex-row">
        <aside
          aria-label="题目导航"
          className="shrink-0 space-y-4 border-b border-border bg-sidebar p-5 lg:w-[236px] lg:border-r lg:border-b-0"
        >
          <h3 className="text-sm font-semibold">题目导航</h3>
          <div className="grid grid-cols-5 gap-2 lg:grid-cols-4">
            {attempt.questions.map((q, i) => (
              <Button
                key={q.question_id}
                size="sm"
                variant={q.question_id === current ? "brand" : "outline"}
                className={cn(
                  "px-0",
                  attempt.submissions.some((s) => s.question_id === q.question_id)
                    ? "text-success"
                    : "",
                )}
                aria-label={`第${i + 1}题`}
                aria-current={q.question_id === current ? "step" : undefined}
                disabled={busy || submit.isPending}
                onClick={() => {
                  void navigate(q.question_id);
                }}
              >
                {i + 1}
              </Button>
            ))}
          </div>
          <p className="border-t border-border pt-3 text-xs leading-6 text-[#496B86]">
            答案保存成功后可刷新或从历史继续；本次练习不计时。
          </p>
        </aside>
        <section className="min-w-0 flex-1 space-y-5 px-4 py-[30px] xl:px-[54px]">
          <div className="flex flex-wrap gap-2 text-xs">
            {[
              String(index + 1).padStart(2, "0"),
              questionLabels[question.type],
              difficultyLabels[question.difficulty ?? "medium"],
              ...(full != null ? [`满分 ${full} 分`] : []),
            ].map((label) => (
              <span key={label} className="rounded-md border border-border bg-surface px-2 py-1">
                {label}
              </span>
            ))}
          </div>
          <AnswerContent content={question.stem} />
          <QuestionInput
            question={question}
            value={drafts[question.question_id]}
            disabled={locked}
            onChange={change}
          />
          <div className="flex flex-wrap justify-between gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={index === 0 || busy}
              onClick={() => {
                void navigate(attempt.questions[index - 1].question_id);
              }}
            >
              上一题
            </Button>
            <Button
              variant="brand"
              size="sm"
              disabled={index >= attempt.questions.length - 1 || busy}
              onClick={() => {
                void navigate(attempt.questions[index + 1].question_id);
              }}
            >
              下一题
            </Button>
          </div>
          {error ? (
            <div
              role="alert"
              className="space-y-2 rounded-md border border-danger bg-surface p-3 text-sm text-danger"
            >
              <p>{error}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  void recover();
                }}
              >
                读取最新答案
              </Button>
            </div>
          ) : null}
          {attempt.status === "active" ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-muted p-3">
              <p className="text-xs">提交当前题获得点评，之后仍可再次作答。</p>
              <div className="flex gap-2">
                {latest && !editing ? (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy || grading}
                    onClick={() => setEditing(true)}
                  >
                    再次作答
                  </Button>
                ) : (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy || save.isPending}
                      onClick={() => {
                        void flush().catch(() => {});
                      }}
                    >
                      保存答案
                    </Button>
                    <Button
                      variant="brand"
                      size="sm"
                      disabled={
                        busy || submit.isPending || !drafts[current] || !attempt.source_available
                      }
                      onClick={() => {
                        void send();
                      }}
                    >
                      提交本题
                    </Button>
                  </>
                )}
              </div>
            </div>
          ) : null}
          {shown ? (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-3">
                <Select
                  value={shown.submission_id}
                  onValueChange={(id) => {
                    setSelectedSubmission(id);
                    setSelectedGrade("");
                  }}
                >
                  <SelectTrigger aria-label="回答历史" className="w-full sm:w-[180px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {submissions.map((s, i) => (
                      <SelectItem key={s.submission_id} value={s.submission_id}>
                        第 {i + 1} 次回答
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {shown.grades.length ? (
                  <Select value={grade?.id ?? ""} onValueChange={setSelectedGrade}>
                    <SelectTrigger aria-label="点评历史" className="w-full sm:w-[180px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {shown.grades.map((g) => (
                        <SelectItem key={g.id} value={g.id}>
                          点评 v{g.version}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : null}
              </div>
              <div className="border-t border-border pt-3">
                <h3 className="text-xs font-semibold">
                  已提交回答（答案 v{shown.answer_version}）
                </h3>
                <AnswerContent content={answerText(shown.answer)} />
              </div>
              {grading ? (
                <p role="status" className="text-sm">
                  当前点评处理中，已提交回答保留。
                </p>
              ) : shown.run?.status === "failed" ? (
                <p role="alert" className="text-sm text-danger">
                  最近一次评分失败；旧点评保留，不能代表失败的评分。
                </p>
              ) : shown.run?.status === "cancelled" ? (
                <p className="text-sm text-muted-foreground">
                  最近一次评分已取消，已提交回答保留。
                </p>
              ) : null}
              {grade ? (
                <GradePanel
                  key={grade.id}
                  grade={grade}
                  code={question.type === "code_text"}
                  subjective={subjective}
                  onRegrade={
                    subjective && attempt.source_available && !busy && !grading
                      ? (reason) => onRegrade(shown.submission_id, reason)
                      : undefined
                  }
                />
              ) : !grading && subjective && attempt.source_available ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => {
                    void onRegrade(shown.submission_id, "原点评未完成，请复核已提交回答").catch(
                      (e: unknown) => setError(e instanceof Error ? e.message : "重评请求失败"),
                    );
                  }}
                >
                  重新评分
                </Button>
              ) : null}
              {!editing ? (
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">答案讲解</h3>
                  <AnswerContent content={question.answer_explanation} />
                </div>
              ) : null}
            </div>
          ) : null}
          <SourceLinks
            setId={attempt.set_id}
            revisionId={attempt.revision_id}
            question={question}
            available={attempt.source_available}
          />
          <FeedbackButtons
            key={`${attempt.revision_id}:${question.question_id}`}
            target={{ revision_id: attempt.revision_id, question_id: question.question_id }}
            value={attempt.question_feedback?.[question.question_id] ?? null}
          />
        </section>
      </div>
    </div>
  );
}
