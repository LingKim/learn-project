"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { AnswerContent } from "@/features/learning/answer-content";
import type { AttemptView, ReportView } from "./api";
import { GradePanel, gradeLabels, answerText } from "./grade-panel";
import { SourceLinks } from "./source-links";
import { isActiveRun } from "./queries";

export function ReportPanel({
  report,
  attempt,
  busy,
  onRegrade,
  onPracticeAgain,
}: {
  report: ReportView;
  attempt: AttemptView;
  busy: boolean;
  onRegrade: (id: string, reason: string) => Promise<void>;
  onPracticeAgain: () => void;
}) {
  const [wrongOnly, setWrongOnly] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [versions, setVersions] = useState<Record<string, string>>({});
  return (
    <div className="mt-5 space-y-[18px]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">本次练习报告</h2>
        <Button variant="brand" disabled={busy} onClick={onPracticeAgain}>
          再练一次
        </Button>
      </div>
      <dl className="grid grid-cols-2 border-y border-border py-5 text-sm sm:grid-cols-4">
        {[
          ["已提交", `${report.submitted_count} / ${report.total_questions}`],
          ["已评分", `${report.graded_count} / ${report.total_questions}`],
          ["未提交", String(report.total_questions - report.submitted_count)],
          [
            "总分",
            report.score != null && report.max_score != null
              ? `${report.score} / ${report.max_score}`
              : "未满足汇总评分条件",
          ],
        ].map(([title, value]) => (
          <div key={title} className="space-y-2 px-2 py-2">
            <dt className="text-xs text-muted-foreground">{title}</dt>
            <dd className="font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="grid min-w-0 gap-7 xl:grid-cols-[minmax(0,1fr)_300px]">
        <section className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-[17px] font-bold">逐题结果</h3>
            <div className="flex gap-2">
              <Button
                variant={wrongOnly ? "ghost" : "brand"}
                size="sm"
                onClick={() => setWrongOnly(false)}
              >
                全部题目
              </Button>
              <Button
                variant={wrongOnly ? "brand" : "ghost"}
                size="sm"
                onClick={() => setWrongOnly(true)}
              >
                仅看错题
              </Button>
            </div>
          </div>
          {report.questions
            .filter((q) => !wrongOnly || ["incorrect", "partial"].includes(q.status))
            .map((row) => {
              const question = attempt.questions.find((q) => q.question_id === row.question_id);
              const submissions = attempt.submissions.filter(
                (s) => s.question_id === row.question_id,
              );
              const latest = row.submission;
              const grade =
                latest?.grades.find((g) => g.id === versions[row.question_id]) ??
                latest?.grades.at(-1);
              if (!question) return null;
              return (
                <section
                  key={row.question_id}
                  className="min-w-0 rounded-lg border border-border bg-surface p-3"
                >
                  <div className="flex flex-wrap gap-3">
                    <span className="rounded-md bg-muted px-2 py-1 text-xs font-semibold">
                      {gradeLabels[row.status]}
                    </span>
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left text-sm font-semibold"
                      aria-expanded={expanded === row.question_id}
                      onClick={() =>
                        setExpanded((old) => (old === row.question_id ? null : row.question_id))
                      }
                    >
                      <span className="line-clamp-2">{question.stem}</span>
                    </button>
                  </div>
                  {isActiveRun(latest?.run) ? (
                    <p role="status" className="mt-2 text-xs">
                      最新评分处理中
                    </p>
                  ) : latest?.run?.status === "failed" ? (
                    <p role="alert" className="mt-2 text-xs text-danger">
                      最新评分失败；旧版本保留。
                    </p>
                  ) : latest?.run?.status === "cancelled" ? (
                    <p className="mt-2 text-xs text-muted-foreground">最新评分已取消</p>
                  ) : null}
                  {expanded === row.question_id ? (
                    <div className="mt-4 space-y-4">
                      <AnswerContent content={question.stem} />
                      {latest ? (
                        <div>
                          <h4 className="text-xs font-semibold">
                            本次提交回答（答案 v{latest.answer_version}）
                          </h4>
                          <AnswerContent content={answerText(latest.answer)} />
                        </div>
                      ) : (
                        <p className="text-sm">未提交。本报告不会把草稿当作已提交回答。</p>
                      )}
                      {latest && latest.grades.length > 1 ? (
                        <div className="flex flex-wrap gap-2">
                          {latest.grades.map((g) => (
                            <Button
                              key={g.id}
                              variant={g.id === grade?.id ? "brand" : "outline"}
                              size="sm"
                              onClick={() =>
                                setVersions((old) => ({ ...old, [row.question_id]: g.id }))
                              }
                            >
                              点评 v{g.version}
                            </Button>
                          ))}
                        </div>
                      ) : null}
                      {grade ? (
                        <GradePanel
                          key={grade.id}
                          grade={grade}
                          code={question.type === "code_text"}
                          subjective={
                            question.type === "short_answer" || question.type === "code_text"
                          }
                          onRegrade={
                            attempt.source_available && !busy && !isActiveRun(latest?.run)
                              ? (reason) => onRegrade(grade.submission_id, reason)
                              : undefined
                          }
                        />
                      ) : latest &&
                        attempt.source_available &&
                        ["short_answer", "code_text"].includes(question.type) ? (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={busy || isActiveRun(latest.run)}
                          onClick={() => {
                            void onRegrade(
                              latest.submission_id,
                              "原点评未完成，请复核已提交回答",
                            ).catch(() => {});
                          }}
                        >
                          重新评分
                        </Button>
                      ) : null}
                      <SourceLinks
                        setId={attempt.set_id}
                        revisionId={attempt.revision_id}
                        question={question}
                        available={attempt.source_available}
                      />
                      {submissions.length > 1 ? (
                        <div className="space-y-2 border-t border-border pt-3">
                          <h4 className="text-xs font-semibold">历史回答</h4>
                          {submissions.slice(0, -1).map((s, i) => (
                            <div key={s.submission_id}>
                              <p className="text-xs">
                                第 {i + 1} 次回答 · 答案 v{s.answer_version}
                              </p>
                              <AnswerContent content={answerText(s.answer)} />
                              {s.grades.map((g) => (
                                <GradePanel
                                  key={g.id}
                                  grade={g}
                                  subjective={
                                    question.type === "short_answer" ||
                                    question.type === "code_text"
                                  }
                                  code={question.type === "code_text"}
                                />
                              ))}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </section>
              );
            })}
          {wrongOnly &&
          !report.questions.some((q) => ["incorrect", "partial"].includes(q.status)) ? (
            <p className="text-sm text-muted-foreground">本次没有已判为错误或部分正确的题目。</p>
          ) : null}
        </section>
        <aside className="min-w-0 space-y-4">
          <h3 className="text-base font-bold">本次知识点结果</h3>
          {report.topics.map((topic) => (
            <section key={topic.topic} className="space-y-2 border-t border-border py-3">
              <h4 className="text-sm font-semibold">{topic.topic}</h4>
              <p className="text-xs leading-6 text-muted-foreground">
                正确 {topic.correct ?? 0} · 部分正确 {topic.partial ?? 0} · 错误{" "}
                {topic.incorrect ?? 0} · 未评分 {topic.ungraded ?? 0} · 未提交{" "}
                {topic.unsubmitted ?? 0}
              </p>
              {topic.insufficient_sample ? (
                <p className="text-xs text-[#496B86]">样本不足，不推断长期掌握度。</p>
              ) : null}
              {topic.error_reasons?.length ? (
                <div>
                  <p className="text-xs font-semibold">错误原因</p>
                  {topic.error_reasons.map((reason, i) => (
                    <AnswerContent key={i} content={reason} />
                  ))}
                </div>
              ) : null}
              {topic.suggestions?.length ? (
                <div>
                  <p className="text-xs font-semibold">改进建议</p>
                  {topic.suggestions.map((suggestion, i) => (
                    <AnswerContent key={i} content={suggestion} />
                  ))}
                </div>
              ) : null}
            </section>
          ))}
          <p className="rounded-lg border border-[#D7E3EA] bg-[#EDF3F7] p-3 text-xs leading-6 text-[#496B86]">
            只总结本次练习证据，样本不足不推断长期掌握度。
            {report.source_mode === "general" ? "本报告基于模型通用知识。" : "本报告基于本人资料。"}
          </p>
        </aside>
      </div>
    </div>
  );
}
