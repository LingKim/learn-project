"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AnswerContent } from "@/features/learning/answer-content";
import { userProfileKeys } from "@/features/user-profile/queries";
import type { EvidenceView, WeaknessView, WeaknessCreate, WeaknessPatch } from "./api";
import { AssetLayout, masteryLabels, severityLabels, practiceTargetHref } from "./asset-layout";
import { WeaknessForm } from "./weakness-form";
import { CardContent } from "./card-content";
import { CardSources } from "./card-sources";
import { KnowledgeStatus } from "./knowledge-status";
import { ReviewHistory } from "./review-history";
import {
  learningAssetKeys,
  weaknessOptions,
  explanationOptions,
  explanationCardOptions,
  confirmWeaknessOptions,
  ignoreWeaknessOptions,
  revokeWeaknessOptions,
  masteryWeaknessOptions,
  patchWeaknessOptions,
  deleteWeaknessOptions,
  regenerateExplanationOptions,
} from "./queries";

export function WeaknessPage({ id }: { id: string }) {
  const router = useRouter();
  const client = useQueryClient();
  const detail = useQuery(weaknessOptions(id));
  const item = detail.data;
  const explanation = useQuery(explanationOptions(item?.explanation_id ?? ""));
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const historical = useQuery(
    explanationCardOptions(item?.explanation_id ?? "", selectedVersion ?? 0),
  );
  const [editing, setEditing] = useState<WeaknessView | null>(null);
  const confirm = useMutation(confirmWeaknessOptions());
  const ignore = useMutation(ignoreWeaknessOptions());
  const revoke = useMutation(revokeWeaknessOptions());
  const mastery = useMutation(masteryWeaknessOptions());
  const patch = useMutation(patchWeaknessOptions());
  const remove = useMutation(deleteWeaknessOptions(client));
  const regenerate = useMutation(regenerateExplanationOptions());
  const busy =
    confirm.isPending ||
    ignore.isPending ||
    revoke.isPending ||
    mastery.isPending ||
    patch.isPending ||
    remove.isPending ||
    regenerate.isPending;
  const error =
    confirm.error ??
    ignore.error ??
    revoke.error ??
    mastery.error ??
    remove.error ??
    regenerate.error;
  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: learningAssetKeys.all }),
      client.invalidateQueries({ queryKey: userProfileKeys.detail() }),
    ]);
  }
  async function decision(kind: "confirm" | "ignore" | "revoke") {
    if (!item) return;
    const input = { id, body: { expected_version: item.version } };
    if (kind === "confirm")
      await confirm.mutateAsync({
        ...input,
        body: { ...input.body, request_key: crypto.randomUUID() },
      });
    else if (kind === "ignore") await ignore.mutateAsync(input);
    else await revoke.mutateAsync(input);
    await refresh();
  }
  async function save(body: Omit<WeaknessCreate, "request_key"> | WeaknessPatch) {
    if (!("expected_version" in body)) return;
    await patch.mutateAsync({ id, body });
    setEditing(null);
    await refresh();
  }
  async function changeMastery(state: WeaknessView["mastery_state"]) {
    if (!item) return;
    await mastery.mutateAsync({
      id,
      body: { expected_version: item.version, mastery_state: state },
    });
    await refresh();
  }
  async function generate() {
    if (!explanation.data) return;
    await regenerate.mutateAsync({
      id: explanation.data.id,
      body: { expected_version: explanation.data.version, request_key: crypto.randomUUID() },
    });
    await refresh();
  }
  async function deleteItem() {
    if (!item) return;
    await remove.mutateAsync({ id, version: item.version });
    router.push("/weaknesses");
  }
  const card = selectedVersion !== null ? historical.data : item?.card;
  return (
    <AssetLayout>
      <Link href="/weaknesses" className="text-xs text-muted-foreground hover:underline">
        返回难点资产库
      </Link>
      {detail.isPending ? (
        <p role="status" className="py-8 text-sm">
          正在读取难点…
        </p>
      ) : detail.error || !item ? (
        <div className="space-y-3 py-8">
          <p role="alert" className="text-sm text-danger">
            {detail.error?.message ?? "难点不可用"}
          </p>
          <Button
            variant="outline"
            onClick={() => {
              void detail.refetch();
            }}
          >
            重新读取
          </Button>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-bold">{item.title}</h1>
              <p className="mt-1 text-xs text-muted-foreground">
                {[item.domain, ...item.tags].filter(Boolean).join(" / ")} · 严重度
                {severityLabels[item.severity]} ·{" "}
                {item.decision === "pending"
                  ? "候选待确认"
                  : item.decision === "ignored"
                    ? "候选已忽略"
                    : item.decision === "revoked"
                      ? "已撤销识别"
                      : masteryLabels[item.mastery_state]}
              </p>
            </div>
            {item.decision === "confirmed" ? (
              <div className="flex flex-wrap gap-2" aria-label="难点掌握状态">
                {Object.entries(masteryLabels).map(([value, label]) => (
                  <Button
                    key={value}
                    size="sm"
                    variant={item.mastery_state === value ? "brand" : "outline"}
                    aria-pressed={item.mastery_state === value}
                    disabled={busy}
                    onClick={() => {
                      void changeMastery(value as WeaknessView["mastery_state"]).catch(() => {});
                    }}
                  >
                    {label}
                  </Button>
                ))}
              </div>
            ) : null}
          </header>
          {item.decision === "pending" ? (
            <section className="space-y-3 rounded-lg border border-border bg-sidebar p-4">
              <h2 className="text-sm font-semibold">候选待确认</h2>
              <p className="text-xs leading-6 text-muted-foreground">
                {item.evidence_sufficient
                  ? "已满足当前证据策略，请结合来源决定是否保留。"
                  : "单次错误、低置信度或多知识点整体结果尚不足以确认长期薄弱，请先查看证据。"}
              </p>
              <div className="flex flex-wrap gap-3">
                <Button
                  variant="brand"
                  disabled={busy}
                  onClick={() => {
                    void decision("confirm").catch(() => {});
                  }}
                >
                  确认入库
                </Button>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    void decision("ignore").catch(() => {});
                  }}
                >
                  忽略本次候选
                </Button>
              </div>
            </section>
          ) : null}
          {!item.source_available ? (
            <p className="rounded-md border border-border bg-sidebar p-3 text-xs leading-6 text-muted-foreground">
              来源不可用：证据原文预览已隐藏，已保存卡片与历史保留。明确重新生成时将核对同一范围的当前有效来源。
            </p>
          ) : null}
          {item.run ? <KnowledgeStatus run={item.run} /> : null}
          {error ? (
            <p role="alert" className="text-sm text-danger">
              {error.message}
            </p>
          ) : null}
          <div className="grid min-w-0 gap-[22px] xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="min-w-0 space-y-4">
              <section>
                <h2 className="mb-2 text-base font-bold">来源证据</h2>
                <p className="mb-2 text-xs text-muted-foreground">
                  策略 {item.policy_version} ·{" "}
                  {item.evidence_sufficient ? "当前证据充分" : "当前证据支持不足"}
                </p>
                <p className="mb-2 text-xs leading-6 text-muted-foreground">
                  自动入库门槛：30 天内至少 3 道不同的中等或困难单知识点题出错，跨至少 2
                  次练习，最近两道有效题仍出错。低置信度或整体归因未验证的结果需明确确认。
                </p>
                {item.evidence.length ? (
                  <ul className="divide-y divide-border border-y border-border">
                    {item.evidence.map((evidence) => (
                      <Evidence key={evidence.id} evidence={evidence} />
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-muted-foreground">暂无可用证据。</p>
                )}
              </section>
              <section>
                <header className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-base font-bold">知识卡片</h2>
                  <div className="flex flex-wrap gap-2">
                    {item.card_versions?.map((version) => (
                      <Button
                        key={version}
                        size="sm"
                        variant={
                          version === (selectedVersion ?? item.active_card_version)
                            ? "brand"
                            : "outline"
                        }
                        onClick={() =>
                          setSelectedVersion(version === item.active_card_version ? null : version)
                        }
                      >
                        版本 {version}
                      </Button>
                    ))}
                  </div>
                </header>
                {historical.error ? (
                  <p role="alert" className="text-sm text-danger">
                    {historical.error.message}
                  </p>
                ) : selectedVersion !== null && historical.isPending ? (
                  <p role="status" className="text-xs">
                    正在读取卡片版本…
                  </p>
                ) : card ? (
                  <>
                    <CardContent key={card.id} card={card} />
                    <CardSources
                      key={`${card.id}:${item.source_available}`}
                      card={card}
                      sourceAvailable={item.source_available}
                    />
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    暂无已发布卡片，首次生成或明确重试后会保存在这里。
                  </p>
                )}
              </section>
            </div>
            <aside className="min-w-0 space-y-4">
              <ReviewHistory kind="weakness" id={id} />
              <div className="flex flex-wrap gap-2 xl:flex-col">
                {item.decision === "confirmed" ? (
                  <>
                    <Button asChild variant="brand" disabled={!item.source_available}>
                      <Link
                        aria-disabled={!item.source_available}
                        href={
                          item.source_available
                            ? practiceTargetHref("weakness", item.id, item.version)
                            : "#"
                        }
                      >
                        针对性再练
                      </Link>
                    </Button>
                    <Button
                      variant="outline"
                      disabled={busy || !explanation.data}
                      onClick={() => {
                        void generate().catch(() => {});
                      }}
                    >
                      重新生成卡片
                    </Button>
                  </>
                ) : null}
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    patch.reset();
                    setEditing(item);
                  }}
                >
                  编辑难点
                </Button>
                {item.decision === "confirmed" ? (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => {
                      void decision("revoke").catch(() => {});
                    }}
                  >
                    撤销识别
                  </Button>
                ) : null}
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    void deleteItem().catch(() => {});
                  }}
                >
                  删除难点
                </Button>
              </div>
              <section>
                <h2 className="mb-2 text-sm font-semibold">状态与识别历史</h2>
                <ul className="space-y-2 text-xs text-muted-foreground">
                  {item.events.map((event) => (
                    <li key={event.id}>
                      {new Date(event.created_at).toLocaleString("zh-CN")} ·{" "}
                      {eventLabel(event.event_type)} · 版本 {event.version}
                    </li>
                  ))}
                </ul>
              </section>
            </aside>
          </div>
        </div>
      )}
      <Dialog
        open={Boolean(editing)}
        onOpenChange={(open) => {
          if (!open && !patch.isPending) setEditing(null);
        }}
      >
        <DialogContent className="max-h-[90dvh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>编辑难点</DialogTitle>
            <DialogDescription>
              编辑名称、领域、标签与严重度，来源范围保持创建时的选择。
            </DialogDescription>
          </DialogHeader>
          {editing ? (
            <WeaknessForm
              initial={editing}
              pending={patch.isPending}
              error={patch.error?.message}
              onCancel={() => setEditing(null)}
              onSubmit={(body) => {
                void save(body).catch(() => {});
              }}
            />
          ) : null}
          {patch.error ? (
            <Button
              variant="outline"
              onClick={() => {
                void detail.refetch().then((result) => {
                  if (result.data) setEditing(result.data);
                });
              }}
            >
              读取最新版本并保留输入
            </Button>
          ) : null}
        </DialogContent>
      </Dialog>
    </AssetLayout>
  );
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
function Evidence({ evidence }: { evidence: EvidenceView }) {
  const question = record(evidence.detail?.question);
  const answer = record(evidence.detail?.answer);
  const stem = typeof question?.stem === "string" ? question.stem : "";
  const answerContent =
    typeof answer?.text === "string"
      ? answer.text
      : typeof answer?.option_id === "string"
        ? answer.option_id
        : Array.isArray(answer?.option_ids)
          ? answer.option_ids
              .filter((value): value is string => typeof value === "string")
              .join(", ")
          : typeof answer?.value === "boolean"
            ? answer.value
              ? "正确"
              : "错误"
            : "";
  return (
    <li className="space-y-2 py-3 text-xs">
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">
          {evidence.kind === "manual"
            ? "用户主动学习目标"
            : `练习评分版本 ${evidence.grade_version ?? "未知"}`}
        </Badge>
        {evidence.superseded ? <Badge variant="outline">已被新评分替代</Badge> : null}
        {evidence.ignored ? <Badge variant="outline">已忽略</Badge> : null}
        {evidence.detail?.low_confidence === true ? (
          <Badge variant="outline">低置信度</Badge>
        ) : null}
        {evidence.detail?.attribution === "whole_question_unverified" ? (
          <Badge variant="outline">多知识点整体关联，归因未验证</Badge>
        ) : null}
      </div>
      {evidence.available ? (
        evidence.kind === "manual" ? (
          <p className="text-muted-foreground">用户手动创建，不参与系统重复错误或验证门槛。</p>
        ) : (
          <>
            <p className="text-muted-foreground">
              {typeof evidence.detail?.difficulty === "string"
                ? (difficultyText[evidence.detail.difficulty] ?? "难度未知")
                : "难度未知"}{" "}
              ·{" "}
              {typeof evidence.detail?.level === "string"
                ? (gradeText[evidence.detail.level] ?? "结果待核验")
                : "结果待核验"}{" "}
              ·{" "}
              {evidence.submitted_at
                ? new Date(evidence.submitted_at).toLocaleString("zh-CN")
                : "提交时间不可用"}
            </p>
            {stem ? <AnswerContent content={stem} /> : null}
            {answerContent ? (
              <div>
                <p className="font-semibold">当时提交的回答</p>
                <AnswerContent content={answerContent} />
              </div>
            ) : null}
            {evidence.attempt_id && typeof evidence.detail?.set_id === "string" ? (
              <Link
                href={`/learning/practice/${evidence.detail.set_id}?attempt=${evidence.attempt_id}&view=report`}
                className="text-accent-foreground hover:underline"
              >
                查看练习来源
              </Link>
            ) : null}
          </>
        )
      ) : (
        <p className="text-muted-foreground">来源已不可用，原文和回答不显示。</p>
      )}
    </li>
  );
}
function eventLabel(value: string) {
  const labels: Record<string, string> = {
    manual_created: "手动创建",
    confirmed: "确认入库",
    ignored: "忽略候选",
    revoked: "撤销识别",
    mastery_changed: "掌握状态变更",
    edited: "编辑难点",
    evidence_updated: "证据更新",
    evidence_corrected: "证据修正",
    auto_confirmed: "策略入库",
  };
  return labels[value] ?? "资产记录";
}
const difficultyText: Record<string, string> = { easy: "简单", medium: "中等", hard: "困难" };
const gradeText: Record<string, string> = {
  correct: "正确",
  incorrect: "错误",
  partial: "部分正确",
};
