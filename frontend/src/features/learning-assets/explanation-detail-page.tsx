"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import type { ExplanationConfig, ExplanationDetail } from "./api";
import {
  AssetLayout,
  ExplanationModes,
  depthLabels,
  foundationLabels,
  practiceTargetHref,
} from "./asset-layout";
import { CardContent } from "./card-content";
import { CardSources } from "./card-sources";
import { ExplanationForm } from "./explanation-form";
import { KnowledgeStatus } from "./knowledge-status";
import { ReviewHistory } from "./review-history";
import { userProfileQueryOptions } from "@/features/user-profile/queries";
import { ApiError } from "@/lib/api/errors";
import { readKnowledgeRequest, writeKnowledgeRequest } from "./request-recovery";
import {
  explanationOptions,
  explanationCardOptions,
  knowledgeRunOptions,
  regenerateExplanationOptions,
  deleteExplanationOptions,
  learningAssetKeys,
  weaknessOptions,
  knowledgeLookupOptions,
} from "./queries";

export function ExplanationDetailPage({ id, runId = "" }: { id: string; runId?: string }) {
  const profile = useQuery(userProfileQueryOptions());
  const owner = profile.data?.username ?? "";
  // 账号和精讲决定恢复、历史选择及编辑快照的归属；路由复用不能把这些状态带到另一份精讲。
  return (
    <ExplanationDetailContent
      key={JSON.stringify([owner, id])}
      id={id}
      runId={runId}
      owner={owner}
    />
  );
}

function ExplanationDetailContent({
  id,
  runId,
  owner,
}: {
  id: string;
  runId: string;
  owner: string;
}) {
  const client = useQueryClient();
  const router = useRouter();
  const detail = useQuery(explanationOptions(id));
  const item = detail.data;
  const checkedSince = useRef(Date.now());
  const [recoveryKey, setRecoveryKey] = useState("");
  const lookup = useQuery(knowledgeLookupOptions(recoveryKey));
  const linkedWeakness = useQuery(weaknessOptions(item?.weakness_id ?? ""));
  const [runState, setRunState] = useState({ linkedRunId: runId, value: runId });
  const runOverride = runState.linkedRunId === runId ? runState.value : runId;
  function setRunOverride(value: string) {
    setRunState({ linkedRunId: runId, value });
  }
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const runQuery = useQuery(knowledgeRunOptions(runOverride));
  const run =
    runOverride && runOverride !== runId
      ? (runQuery.data ?? item?.run)
      : (item?.run ?? runQuery.data);
  const currentVerified = detail.dataUpdatedAt >= checkedSince.current;
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const version =
    selectedVersion ?? (run?.status === "succeeded" ? run.result_ref?.version : undefined) ?? 0;
  const historical = useQuery(explanationCardOptions(id, version));
  const [adjusting, setAdjusting] = useState<ExplanationDetail | null>(null);
  const keys = useRef(new Map<string, string>());
  const regenerate = useMutation(regenerateExplanationOptions());
  const remove = useMutation(deleteExplanationOptions(client));
  const card = version ? historical.data : item?.card;
  useEffect(() => {
    if (owner) setRecoveryKey(readKnowledgeRequest(sessionStorage, owner, id));
  }, [owner, id]);
  useEffect(() => {
    if (!lookup.data || lookup.data.explanation_id !== id) return;
    writeKnowledgeRequest(sessionStorage, owner, id, "");
    setRecoveryKey("");
    setRunOverride(lookup.data.id);
    setSelectedVersion(null);
    setAdjusting(null);
    regenerate.reset();
    client.setQueryData(learningAssetKeys.run(lookup.data.id), lookup.data);
    void client.invalidateQueries({ queryKey: learningAssetKeys.explanation(id) });
    router.replace(`/learning/explanation/${id}?run=${lookup.data.id}`);
  }, [lookup.data, owner, id, client, router, regenerate.reset]);
  function startAdjusting() {
    if (!item || (item.weakness_id && !linkedWeakness.data)) return;
    regenerate.reset();
    setAdjusting({
      ...item,
      config: { ...item.config, topic: linkedWeakness.data?.title ?? item.topic },
    });
  }
  async function generate(config?: ExplanationConfig) {
    const snapshot = adjusting ?? item;
    if (!snapshot) return;
    const body = { expected_version: snapshot.version, ...(config ? { config } : {}) };
    const signature = JSON.stringify(body);
    let requestKey = keys.current.get(signature);
    if (!requestKey) {
      requestKey = crypto.randomUUID();
      keys.current.set(signature, requestKey);
    }
    writeKnowledgeRequest(sessionStorage, owner, id, requestKey);
    let result;
    try {
      result = await regenerate.mutateAsync({ id, body: { ...body, request_key: requestKey } });
    } catch (error) {
      if (error instanceof ApiError && (error.status ?? 0) >= 400) {
        writeKnowledgeRequest(sessionStorage, owner, id, "");
        setRecoveryKey("");
      } else setRecoveryKey(requestKey);
      throw error;
    }
    writeKnowledgeRequest(sessionStorage, owner, id, "");
    if (!active.current) return;
    setRecoveryKey("");
    client.setQueryData(learningAssetKeys.run(result.data.run.id), result.data.run);
    client.setQueryData<ExplanationDetail>(learningAssetKeys.explanation(id), (old) =>
      old ? { ...old, ...result.data.explanation, run: result.data.run } : old,
    );
    setRunOverride(result.data.run.id);
    setSelectedVersion(null);
    setAdjusting(null);
    router.replace(`/learning/explanation/${id}?run=${result.data.run.id}`);
    await client.invalidateQueries({ queryKey: learningAssetKeys.all });
  }
  async function deleteItem() {
    if (!item) return;
    await remove.mutateAsync({ id, version: item.version });
    router.push("/learning/explanation");
  }
  return (
    <AssetLayout>
      <Link href="/learning/explanation" className="text-xs text-muted-foreground hover:underline">
        返回知识精讲
      </Link>
      {detail.isPending ? (
        <p role="status" className="py-8 text-sm">
          正在读取精讲…
        </p>
      ) : detail.error || !item ? (
        <div className="space-y-3 py-8">
          <p role="alert" className="text-sm text-danger">
            {detail.error?.message ?? "精讲不可用"}
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
        <>
          <header className="my-[18px] flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-bold">{item.topic}</h1>
              <p className="mt-1 text-xs text-muted-foreground">
                {foundationLabels[card?.foundation ?? item.config.foundation ?? "know_concept"]} ·{" "}
                {depthLabels[card?.depth ?? item.config.depth ?? "systematic"]} ·{" "}
                {item.config.source_mode === "materials" ? "资料模式" : "模型通用知识"} ·{" "}
                {card ? `卡片版本 ${card.version}` : "暂无已发布卡片"}
              </p>
              {item.weakness_id ? (
                <Link
                  href={`/weaknesses/${item.weakness_id}`}
                  className="mt-1 block text-xs text-accent-foreground hover:underline"
                >
                  查看关联难点
                </Link>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={regenerate.isPending || Boolean(item.weakness_id && !linkedWeakness.data)}
                onClick={() => {
                  regenerate.reset();
                  void generate().catch(() => {});
                }}
              >
                重新生成
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={regenerate.isPending || Boolean(item.weakness_id && !linkedWeakness.data)}
                onClick={() => {
                  startAdjusting();
                }}
              >
                调整配置
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                onClick={() => {
                  void deleteItem().catch(() => {});
                }}
              >
                删除精讲
              </Button>
            </div>
          </header>
          <ExplanationModes />
          {!item.source_available ? (
            <p className="mt-4 rounded-md border border-border bg-sidebar p-3 text-xs text-muted-foreground">
              来源已失效，原文预览不可用，已保存文字卡片保留。重新生成会核对当前资料范围。
            </p>
          ) : null}
          {recoveryKey && lookup.isPending ? (
            <p role="status" className="my-3 text-xs">
              正在恢复已提交的精讲任务…
            </p>
          ) : null}
          {!currentVerified ? (
            <p role="status" className="my-3 text-xs">
              正在核对当前精讲任务…
            </p>
          ) : run ? (
            <KnowledgeStatus
              run={run}
              onAdjust={item.weakness_id && !linkedWeakness.data ? undefined : startAdjusting}
            />
          ) : null}
          {linkedWeakness.error ? (
            <p role="alert" className="mt-3 text-sm text-danger">
              {linkedWeakness.error.message}
            </p>
          ) : null}
          {runQuery.error ? (
            <p role="alert" className="mt-3 text-sm text-danger">
              {runQuery.error.message}
            </p>
          ) : null}
          {regenerate.error || remove.error ? (
            <p role="alert" className="mt-3 text-sm text-danger">
              {regenerate.error?.message ?? remove.error?.message}
            </p>
          ) : null}
          {adjusting ? (
            <section className="mt-5 border-y border-border py-5">
              <div className="flex items-center justify-between gap-3">
                <h2 className="font-semibold">调整精讲配置</h2>
                <Button variant="outline" size="sm" onClick={() => setAdjusting(null)}>
                  返回结果
                </Button>
              </div>
              <ExplanationForm
                key={`edit:${id}`}
                initial={adjusting.config}
                fixedSource={Boolean(item.weakness_id)}
                pending={regenerate.isPending}
                error={regenerate.error?.message}
                onSubmit={(config) => {
                  void generate(config).catch(() => {});
                }}
              />
              {item.weakness_id ? (
                <p className="mt-3 text-xs text-muted-foreground">
                  绑定难点的资料范围不可改变；请在原范围内调整基础、深度和语言。
                </p>
              ) : null}
              {regenerate.error ? (
                <Button
                  className="mt-3"
                  variant="outline"
                  onClick={() => {
                    void detail.refetch().then((result) => {
                      if (result.data)
                        setAdjusting((old) =>
                          old ? { ...old, version: result.data.version } : null,
                        );
                    });
                  }}
                >
                  读取最新版本并保留输入
                </Button>
              ) : null}
            </section>
          ) : null}
          <section className="mt-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-2 text-xs font-semibold">卡片历史版本</span>
              {item.card_versions?.map((entry) => (
                <Button
                  key={entry}
                  size="sm"
                  variant={entry === (version || item.active_card_version) ? "brand" : "outline"}
                  onClick={() => setSelectedVersion(entry)}
                >
                  版本 {entry}
                </Button>
              ))}
            </div>
            {historical.error ? (
              <p role="alert" className="mt-4 text-sm text-danger">
                {historical.error.message}
              </p>
            ) : version && historical.isPending ? (
              <p role="status" className="py-6 text-sm">
                正在读取指定版本…
              </p>
            ) : card ? (
              <>
                <CardContent key={card.id} card={card} />
                <CardSources
                  key={`${card.id}:${item.source_available}`}
                  card={card}
                  sourceAvailable={item.source_available}
                />
                <div className="mt-5 flex justify-end">
                  <Button asChild variant="brand" disabled={!item.source_available}>
                    <Link
                      aria-disabled={!item.source_available}
                      href={
                        item.source_available
                          ? practiceTargetHref("explanation", id, card.version)
                          : "#"
                      }
                    >
                      针对性再练
                    </Link>
                  </Button>
                </div>
              </>
            ) : (
              <p className="py-8 text-sm text-muted-foreground">
                暂无已发布卡片，真实任务完成后会显示五部分文字内容。
              </p>
            )}
          </section>
          <div className="mt-8 border-t border-border pt-4">
            <ReviewHistory kind="explanation" id={id} />
          </div>
        </>
      )}
    </AssetLayout>
  );
}
