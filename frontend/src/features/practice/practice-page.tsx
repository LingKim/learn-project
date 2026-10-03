"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2, RefreshCw, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AnswerContent } from "@/features/learning/answer-content";
import { userProfileQueryOptions } from "@/features/user-profile/queries";
import type {
  PracticeConfig,
  PracticeQuestion,
  RunView,
  SubmissionGradeView,
  PlanCandidate,
} from "./api";
import type { MutationResult } from "@/lib/api/protocol";
import { ApiError } from "@/lib/api/errors";
import { PracticeLayout, PracticeModes } from "./practice-layout";
import { ConfigForm, questionLabels, difficultyLabels } from "./config-form";
import { configForEditing } from "./config-editing";
import { QuestionEditor } from "./question-editor";
import { AttemptPanel } from "./attempt-panel";
import { ReportPanel } from "./report-panel";
import { FeedbackButtons } from "./grade-panel";
import { SourceLinks } from "./source-links";
import { RunStatus } from "./run-status";
import {
  readPendingRequest,
  writePendingRequest,
  type PendingPracticeRequest,
} from "./request-recovery";
import {
  practiceListOptions,
  practiceSetOptions,
  practicePlanOptions,
  practiceRevisionOptions,
  practiceAttemptOptions,
  practiceReportOptions,
  practiceGradeOptions,
  practiceRunOptions,
  practiceLookupOptions,
  practiceKeys,
  isActiveRun,
  createPracticeOptions,
  patchPracticeOptions,
  planPracticeOptions,
  generatePracticeOptions,
  regeneratePracticeOptions,
  editQuestionOptions,
  deleteQuestionOptions,
  startAttemptOptions,
  regradeOptions,
  deletePracticeOptions,
} from "./queries";

export function PracticePage({
  setId = "",
  attemptId = "",
  report = false,
  requestKey = "",
  runId = "",
  initialConfig,
  initialTitle,
}: {
  setId?: string;
  attemptId?: string;
  report?: boolean;
  requestKey?: string;
  runId?: string;
  initialConfig?: PracticeConfig;
  initialTitle?: string;
}) {
  const router = useRouter();
  const client = useQueryClient();
  const profile = useQuery(userProfileQueryOptions());
  const owner = profile.data?.username ?? "";
  const [page, setPage] = useState(1);
  const history = useQuery(practiceListOptions(page));
  const detail = useQuery(practiceSetOptions(setId));
  const [view, setView] = useState<"main" | "config">("main");
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<PracticeQuestion | null>(null);
  const [posting, setPosting] = useState(false);
  const requestContext = JSON.stringify([owner, setId, requestKey, runId]);
  const linkedRequest: PendingPracticeRequest | null =
    requestKey || runId
      ? { requestKey, runId: runId || undefined, operation: "", targetId: setId }
      : null;
  const [requestState, setRequestState] = useState(() => ({
    context: requestContext,
    value: linkedRequest,
  }));
  // 页面可被路由复用；旧账号或旧题集的恢复指针不能用于当前上下文的查询。
  const request = requestState.context === requestContext ? requestState.value : linkedRequest;
  const activeContext = useRef(requestContext);
  activeContext.current = requestContext;
  const processed = useRef("");
  const createKey = useRef<{ digest: string; key: string } | null>(null);
  useEffect(() => {
    const value =
      requestKey || runId
        ? { requestKey, runId: runId || undefined, operation: "", targetId: setId }
        : owner && setId
          ? readPendingRequest(sessionStorage, owner, setId)
          : null;
    setRequestState({ context: JSON.stringify([owner, setId, requestKey, runId]), value });
  }, [owner, setId, requestKey, runId]);
  const runQuery = useQuery(practiceRunOptions(request?.runId ?? ""));
  const lookup = useQuery(
    practiceLookupOptions(
      setId,
      request?.requestKey ?? "",
      Boolean(request && !request.runId && !posting),
    ),
  );
  const run = runQuery.data ?? lookup.data;
  const result = run?.status === "succeeded" ? run.result_ref : null;
  const plan = useQuery(practicePlanOptions(setId, result?.type === "plan" ? result.version : 0));
  const revisionQuery = useQuery(
    practiceRevisionOptions(setId, result?.type === "revision" ? result.id : ""),
  );
  const gradeQuery = useQuery(
    practiceGradeOptions(
      result?.type === "grade" ? (run?.submission_id ?? "") : "",
      result?.type === "grade" ? result.version : 0,
    ),
  );
  const attempt = useQuery(practiceAttemptOptions(attemptId));
  const reportQuery = useQuery({
    ...practiceReportOptions(attemptId),
    enabled: Boolean(report && attemptId),
  });
  const revision = result?.type === "revision" ? revisionQuery.data : detail.data?.revision;
  const create = useMutation(createPracticeOptions());
  const patch = useMutation(patchPracticeOptions());
  const makePlan = useMutation(planPracticeOptions());
  const generate = useMutation(generatePracticeOptions());
  const regenerate = useMutation(regeneratePracticeOptions());
  const editQuestion = useMutation(editQuestionOptions());
  const removeQuestion = useMutation(deleteQuestionOptions());
  const start = useMutation(startAttemptOptions());
  const regrade = useMutation(regradeOptions());
  const remove = useMutation(deletePracticeOptions(client));
  const busy = posting || isActiveRun(run);
  useEffect(() => {
    if (!run || run.status !== "succeeded" || !result) return;
    const signature = `${run.id}:${run.attempt_count}:${result.type}:${result.id}:${result.version}`;
    if (processed.current === signature) return;
    processed.current = signature;
    void Promise.all([
      client.invalidateQueries({ queryKey: practiceKeys.set(setId) }),
      client.invalidateQueries({ queryKey: practiceKeys.lists() }),
      ...(attemptId
        ? [
            client.invalidateQueries({ queryKey: practiceKeys.attempt(attemptId) }),
            client.invalidateQueries({ queryKey: practiceKeys.report(attemptId) }),
          ]
        : []),
    ]);
  }, [run, result, setId, attemptId, client]);
  function remember(ref: PendingPracticeRequest | null, id = setId) {
    // 离开旧上下文后的迟到响应不能重写当前页面或跳回旧题集。
    if (activeContext.current !== requestContext) return;
    setRequestState({ context: requestContext, value: ref });
    if (owner && id) writePendingRequest(sessionStorage, owner, id, ref);
    if (id) {
      const query = new URLSearchParams();
      if (attemptId) query.set("attempt", attemptId);
      if (report) query.set("view", "report");
      if (ref?.runId) query.set("run", ref.runId);
      else if (ref?.requestKey) query.set("request", ref.requestKey);
      router.replace(`/learning/practice/${id}${query.size ? `?${query}` : ""}`, { scroll: false });
    }
  }
  function changeRun(value: RunView) {
    const ref = {
      requestKey: value.request_key,
      operation: value.operation,
      targetId: request?.targetId ?? setId,
      runId: value.id,
    };
    remember(ref);
    client.setQueryData(practiceKeys.run(value.id), value);
  }
  async function requestRun(
    operation: RunView["operation"],
    key: string,
    targetId: string,
    action: () => Promise<MutationResult<RunView | SubmissionGradeView>>,
  ) {
    remember({ requestKey: key, operation, targetId });
    setPosting(true);
    setError(null);
    try {
      const response = await action();
      if ("operation" in response.data) changeRun(response.data);
      else {
        remember(null);
        await client.invalidateQueries({ queryKey: practiceKeys.all });
      }
      return response.data;
    } catch (e) {
      // A lost response or replay conflict is recovered with a read; model calls are never retried here.
      try {
        const existing = await client.fetchQuery(practiceLookupOptions(setId, key));
        changeRun(existing);
        return existing;
      } catch {
        setError(e instanceof Error ? e.message : "请求未完成，输入和历史已保留。");
        throw e;
      }
    } finally {
      setPosting(false);
    }
  }
  async function configure(config: PracticeConfig, title: string) {
    setError(null);
    if (!setId) {
      const digest = JSON.stringify([title, config]);
      const key =
        createKey.current?.digest === digest ? createKey.current.key : crypto.randomUUID();
      createKey.current = { digest, key };
      try {
        const created = await create.mutateAsync({ title, config, request_key: key });
        const planKey = crypto.randomUUID();
        if (owner)
          writePendingRequest(sessionStorage, owner, created.data.id, {
            requestKey: planKey,
            operation: "plan",
            targetId: created.data.id,
          });
        try {
          const queued = await makePlan.mutateAsync({
            id: created.data.id,
            body: { expected_version: created.data.version, request_key: planKey },
          });
          if (owner)
            writePendingRequest(sessionStorage, owner, created.data.id, {
              requestKey: planKey,
              operation: "plan",
              targetId: created.data.id,
              runId: queued.data.id,
            });
          router.push(`/learning/practice/${created.data.id}?run=${queued.data.id}`);
        } catch {
          router.push(`/learning/practice/${created.data.id}?request=${planKey}`);
        }
        await client.invalidateQueries({ queryKey: practiceKeys.lists() });
      } catch (e) {
        setError(e instanceof Error ? e.message : "配置未保存");
      }
    } else {
      try {
        const updated = await patch.mutateAsync({
          id: setId,
          body: { expected_version: detail.data?.version ?? 1, title, config },
        });
        await client.invalidateQueries({ queryKey: practiceKeys.set(setId) });
        const key = crypto.randomUUID();
        await requestRun("plan", key, setId, () =>
          makePlan.mutateAsync({
            id: setId,
            body: { expected_version: updated.data.version, request_key: key },
          }),
        );
        setView("main");
      } catch (e) {
        setError(e instanceof Error ? e.message : "配置未保存");
      }
    }
  }
  async function confirm(candidate: "original" | "recommended") {
    if (!plan.data || !detail.data) return;
    const key = crypto.randomUUID();
    await requestRun("generate", key, setId, () =>
      generate.mutateAsync({
        id: setId,
        body: {
          expected_version: detail.data.version,
          request_key: key,
          plan_version: plan.data!.version,
          candidate,
          confirmed_config_digest: plan.data![candidate].config_digest,
        },
      }),
    );
  }
  async function regenerateQuestions(questionId?: string) {
    if (!revision || !detail.data) return;
    const key = crypto.randomUUID();
    await requestRun("regenerate", key, setId, () =>
      regenerate.mutateAsync({
        id: setId,
        body: {
          expected_version: detail.data!.version,
          base_revision_id: revision.id,
          question_id: questionId,
          request_key: key,
        },
      }),
    );
  }
  async function begin() {
    if (!revision || !detail.data) return;
    try {
      const created = await start.mutateAsync({
        id: setId,
        body: {
          expected_version: detail.data.version,
          revision_id: revision.id,
          request_key: crypto.randomUUID(),
        },
      });
      await client.invalidateQueries({ queryKey: practiceKeys.set(setId) });
      router.push(`/learning/practice/${setId}?attempt=${created.data.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "开始练习失败");
    }
  }
  async function regradeAnswer(id: string, reason: string) {
    const key = crypto.randomUUID();
    await requestRun("regrade", key, id, () =>
      regrade.mutateAsync({ id, body: { reason, request_key: key } }),
    );
  }
  async function saveQuestion(question: PracticeQuestion) {
    if (!detail.data) return;
    const result = await editQuestion.mutateAsync({
      id: setId,
      questionId: question.question_id,
      body: { expected_version: detail.data.version, question },
    });
    remember(null);
    client.setQueryData(practiceKeys.revision(setId, result.data.id), result.data);
    await client.invalidateQueries({ queryKey: practiceKeys.set(setId) });
  }
  async function deleteQuestion(questionId: string) {
    if (!detail.data) return;
    try {
      await removeQuestion.mutateAsync({ id: setId, questionId, version: detail.data.version });
      remember(null);
      await client.invalidateQueries({ queryKey: practiceKeys.set(setId) });
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除未成功");
    }
  }
  function adjust() {
    remember(null);
    setView("config");
    setError(null);
  }
  const mainError =
    error ??
    detail.error?.message ??
    attempt.error?.message ??
    reportQuery.error?.message ??
    runQuery.error?.message ??
    (lookup.error && !(lookup.error instanceof ApiError && lookup.error.status === 404)
      ? lookup.error.message
      : null) ??
    plan.error?.message ??
    revisionQuery.error?.message ??
    gradeQuery.error?.message;
  const configView =
    !setId ||
    view === "config" ||
    (!busy && !plan.data && !revision && !attemptId && Boolean(detail.data));
  const title = report
    ? "本次练习报告"
    : attemptId
      ? (detail.data?.title ?? "刷题练习")
      : plan.data && !revision
        ? "确认出题配置"
        : revision
          ? "题目预览"
          : "学习室 · 刷题练习";
  return (
    <PracticeLayout
      answerMode={Boolean(attemptId && !report)}
      history={
        <>
          <div className="space-y-3">
            {history.isPending ? (
              <p role="status" className="text-xs">
                正在读取练习历史…
              </p>
            ) : null}
            {history.error ? (
              <p role="alert" className="text-xs text-danger">
                {history.error.message}
              </p>
            ) : null}
            {history.data?.data.length === 0 ? (
              <p className="text-xs leading-6 text-muted-foreground">
                尚无练习。选择资料或输入知识点，创建第一份练习。
              </p>
            ) : null}
            {history.data?.data.map((set) => (
              <div key={set.id} className="group flex items-start gap-2">
                <Link
                  href={`/learning/practice/${set.id}`}
                  className="min-w-0 flex-1 rounded-md px-2 py-2 text-sm hover:bg-muted"
                >
                  <span className="block truncate font-semibold">{set.title}</span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {set.config.question_count ?? 5} 题 ·{" "}
                    {set.config.source_mode === "materials" ? "资料模式" : "通用知识"}
                  </span>
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  className="px-1"
                  aria-label={`删除练习${set.title}`}
                  disabled={remove.isPending}
                  onClick={() => {
                    void remove
                      .mutateAsync({ id: set.id, version: set.version })
                      .then(() => {
                        if (set.id === setId) router.push("/learning/practice");
                      })
                      .catch((e: unknown) => setError(e instanceof Error ? e.message : "删除失败"));
                  }}
                >
                  <Trash2 aria-hidden="true" className="size-3" />
                </Button>
              </div>
            ))}
          </div>
          {history.data && history.data.meta.total_pages > 1 ? (
            <div className="flex items-center justify-between">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                上一页
              </Button>
              <span className="text-xs">
                {page}/{history.data.meta.total_pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= history.data.meta.total_pages}
                onClick={() => setPage((p) => p + 1)}
              >
                下一页
              </Button>
            </div>
          ) : null}
        </>
      }
    >
      {!(attemptId && !report) ? (
        <header className="mb-[18px] space-y-1">
          <h1 className="text-[26px] font-bold">{title}</h1>
          <p className="text-[13px] text-muted-foreground">
            {configView ? "结合个人资料，基于资料或知识点出题。" : "配置 → 确认 → 题目预览 → 练习"}
          </p>
        </header>
      ) : null}
      {!(attemptId && !report) ? <PracticeModes /> : null}
      {mainError ? (
        <div
          role="alert"
          className="my-4 space-y-2 rounded-md border border-danger bg-surface p-3 text-sm text-danger"
        >
          <p>{mainError}</p>
          {setId ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void client.invalidateQueries({ queryKey: practiceKeys.set(setId) });
              }}
            >
              读取最新配置
            </Button>
          ) : null}
        </div>
      ) : null}
      {setId && detail.isPending ? (
        <p role="status" className="flex items-center gap-2 py-6 text-sm">
          <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
          正在读取练习…
        </p>
      ) : null}
      {run &&
      !(
        run.status === "succeeded" &&
        ((result?.type === "plan" && plan.data) ||
          (result?.type === "revision" && revisionQuery.data) ||
          (result?.type === "grade" && gradeQuery.data))
      ) ? (
        <RunStatus run={run} onChange={changeRun} onAdjust={adjust} />
      ) : null}
      {request &&
      !posting &&
      !run &&
      lookup.error instanceof ApiError &&
      lookup.error.status === 404 ? (
        <div className="my-4 space-y-2 rounded-md border border-border bg-muted p-3">
          <p className="text-sm">未找到对应任务，请读取最新练习状态后明确重新发起。</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              remember(null);
              void client.invalidateQueries({ queryKey: practiceKeys.all });
            }}
          >
            读取最新状态
          </Button>
        </div>
      ) : null}
      {detail.data && !detail.data.source_available ? (
        <p role="alert" className="my-4 rounded-md border border-border bg-muted p-3 text-sm">
          来源已失效，历史题目、回答与点评仍可读，来源预览不可用。请新建练习选择当前有效资料。
        </p>
      ) : null}
      {configView ? (
        <ConfigForm
          key={`${setId}:${detail.data?.version ?? 0}`}
          initial={detail.data ? configForEditing(detail.data) : initialConfig}
          title={detail.data?.title ?? initialTitle}
          fixedSource={Boolean(setId)}
          pending={create.isPending || patch.isPending || makePlan.isPending || busy}
          error={error}
          onConfirm={(config, title) => {
            void configure(config, title);
          }}
        />
      ) : null}
      {!configView && !attemptId && plan.data && result?.type === "plan" ? (
        <div className="mt-5 space-y-4">
          <div className="grid gap-5 md:grid-cols-2">
            {(["original", "recommended"] as const).map((candidate) => (
              <section
                key={candidate}
                className="space-y-4 rounded-lg border border-border bg-surface p-5"
              >
                <h2 className="text-lg font-semibold">
                  {candidate === "original" ? "原配置" : "AI 推荐配置"}
                </h2>
                <CandidateSummary candidate={plan.data![candidate]} />
                <Button
                  variant="brand"
                  disabled={busy || generate.isPending || !detail.data?.source_available}
                  onClick={() => {
                    void confirm(candidate).catch(() => {});
                  }}
                >
                  {candidate === "original" ? "使用原配置生成" : "采用推荐配置生成"}
                </Button>
              </section>
            ))}
          </div>
          {plan.data.suggestions.map((s, i) => (
            <p className="text-sm leading-6" key={i}>
              {s}
            </p>
          ))}
          <p className="text-xs text-muted-foreground">
            需要调整题量、题型或主题？返回修改配置后，再查看更新的方案。
          </p>
          <Button variant="outline" onClick={adjust} disabled={busy}>
            返回修改配置
          </Button>
        </div>
      ) : null}
      {!configView && !attemptId && revision && result?.type !== "plan" ? (
        <div className="mt-5 space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold">
              预览题目 · {revision.questions.length} 题 · 题集 v{revision.version}
            </h2>
            <Button
              variant="outline"
              size="sm"
              disabled={busy || !revision.questions.length || !revision.source_available}
              onClick={() => {
                void regenerateQuestions().catch(() => {});
              }}
            >
              <RefreshCw aria-hidden="true" className="size-4" />
              整组重新生成
            </Button>
          </div>
          <div className="border-t border-border">
            {revision.questions.map((question, i) => (
              <article
                key={question.question_id}
                className="flex min-h-[84px] flex-wrap items-center gap-3 border-b border-border px-2 py-3"
              >
                <span className="grid size-[34px] shrink-0 place-items-center rounded-lg bg-muted text-xs font-bold text-accent-foreground">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="mb-1 text-xs text-muted-foreground">
                    {questionLabels[question.type]} ·{" "}
                    {difficultyLabels[question.difficulty ?? "medium"]}
                  </p>
                  <p className="line-clamp-2 text-sm font-semibold">{question.stem}</p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button
                    aria-label={`编辑第${i + 1}题`}
                    title="编辑题目"
                    variant="outline"
                    size="sm"
                    className="px-2"
                    disabled={busy}
                    onClick={() => setEditing(question)}
                  >
                    <Pencil aria-hidden="true" className="size-4" />
                  </Button>
                  <Button
                    aria-label={`删除第${i + 1}题`}
                    title="删除题目"
                    variant="outline"
                    size="sm"
                    className="px-2"
                    disabled={busy || removeQuestion.isPending}
                    onClick={() => {
                      void deleteQuestion(question.question_id);
                    }}
                  >
                    <Trash2 aria-hidden="true" className="size-4 text-danger" />
                  </Button>
                  <Button
                    aria-label={`重新生成第${i + 1}题`}
                    title="重新生成题目"
                    variant="outline"
                    size="sm"
                    className="px-2"
                    disabled={busy || !revision.source_available}
                    onClick={() => {
                      void regenerateQuestions(question.question_id).catch(() => {});
                    }}
                  >
                    <RefreshCw aria-hidden="true" className="size-4" />
                  </Button>
                </div>
                <details className="w-full pl-[46px]">
                  <summary className="cursor-pointer text-xs text-muted-foreground">
                    查看题目、答案与评分规则
                  </summary>
                  <div className="mt-3 space-y-3">
                    <AnswerContent content={question.stem} />
                    {"options" in question
                      ? question.options.map((o) => (
                          <p key={o.id} className="text-sm">
                            {o.id} · {o.text}
                          </p>
                        ))
                      : null}
                    <p className="text-sm">
                      标准答案：
                      {typeof question.answer === "boolean"
                        ? question.answer
                          ? "正确"
                          : "错误"
                        : Array.isArray(question.answer)
                          ? question.answer.join("；")
                          : question.answer}
                    </p>
                    <AnswerContent content={question.answer_explanation} />
                    {question.rubric.map((r) => (
                      <p key={r.id} className="text-xs">
                        {r.description}
                        {r.max_score != null ? ` · 满分 ${r.max_score} 分` : ""}
                      </p>
                    ))}
                    <SourceLinks
                      setId={setId}
                      revisionId={revision.id}
                      question={question}
                      available={revision.source_available}
                    />
                    <FeedbackButtons
                      key={`${revision.id}:${question.question_id}`}
                      target={{ revision_id: revision.id, question_id: question.question_id }}
                      value={revision.question_feedback?.[question.question_id] ?? null}
                    />
                  </div>
                </details>
              </article>
            ))}
          </div>
          {!revision.questions.length ? (
            <p role="alert" className="text-sm text-muted-foreground">
              题集为空，请返回修改配置并重新生成题目。
            </p>
          ) : null}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button variant="outline" disabled={busy} onClick={adjust}>
              返回修改
            </Button>
            <Button
              variant="brand"
              disabled={
                busy || start.isPending || !revision.questions.length || !revision.source_available
              }
              onClick={() => {
                void begin();
              }}
            >
              开始练习
            </Button>
          </div>
        </div>
      ) : null}
      {detail.data?.attempts.length && !attemptId ? (
        <section className="mt-8 space-y-3 border-t border-border pt-5">
          <h2 className="text-base font-semibold">练习记录</h2>
          {detail.data.attempts.map((a, i) => (
            <div key={a.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <p>
                第 {i + 1} 次练习 · {a.status === "active" ? "进行中" : "已完成"} ·{" "}
                {a.questions.length} 题
              </p>
              <Button asChild size="sm" variant="outline">
                <Link
                  href={`/learning/practice/${setId}?attempt=${a.id}${a.status === "completed" ? "&view=report" : ""}`}
                >
                  {a.status === "active" ? "继续练习" : "查看报告"}
                </Link>
              </Button>
            </div>
          ))}
        </section>
      ) : null}
      {attempt.data && !report ? (
        <AttemptPanel
          key={attempt.data.id}
          attempt={attempt.data}
          title={detail.data?.title ?? "刷题练习"}
          busy={busy}
          resultGrade={gradeQuery.data}
          onRequest={requestRun}
          onRegrade={regradeAnswer}
          onComplete={() =>
            router.push(`/learning/practice/${setId}?attempt=${attemptId}&view=report`)
          }
        />
      ) : null}
      {attempt.data && reportQuery.data && report ? (
        <ReportPanel
          report={reportQuery.data}
          attempt={attempt.data}
          busy={busy}
          onRegrade={regradeAnswer}
          onPracticeAgain={() => router.push(`/learning/practice/${setId}`)}
        />
      ) : null}
      {editing ? (
        <QuestionEditor
          key={editing.question_id}
          question={editing}
          onClose={() => setEditing(null)}
          onSave={saveQuestion}
        />
      ) : null}
    </PracticeLayout>
  );
}
function CandidateSummary({ candidate }: { candidate: PlanCandidate }) {
  return (
    <div className="space-y-3">
      <AnswerContent content={candidate.summary} />
      <p className="text-sm leading-7">
        {candidate.config.question_count} 题 ·{" "}
        {difficultyLabels[candidate.config.difficulty ?? "medium"]}
        <br />
        {Object.entries(candidate.config.question_types ?? {})
          .filter(([, n]) => n > 0)
          .map(([type, n]) => `${questionLabels[type as PracticeQuestion["type"]] ?? type} ${n}`)
          .join(" / ")}
        <br />
        来源：{candidate.config.source_mode === "materials" ? "本人资料" : "模型通用知识"}
        <br />
        知识点：{candidate.config.topic || "按有效学习上下文"}
      </p>
    </div>
  );
}
