"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { userProfileQueryOptions } from "@/features/user-profile/queries";
import type { ExplanationConfig } from "./api";
import { AssetLayout, AssetEmpty, ExplanationModes } from "./asset-layout";
import { ExplanationForm } from "./explanation-form";
import { ApiError } from "@/lib/api/errors";
import { readKnowledgeRequest, writeKnowledgeRequest } from "./request-recovery";
import {
  createExplanationOptions,
  explanationListOptions,
  knowledgeLookupOptions,
  learningAssetKeys,
  weaknessListOptions,
  weaknessOptions,
  explanationOptions,
  regenerateExplanationOptions,
} from "./queries";

export function ExplanationPage({
  weaknessId = "",
  weaknessVersion,
}: {
  weaknessId?: string;
  weaknessVersion?: number;
}) {
  const router = useRouter();
  const client = useQueryClient();
  const [selectedId, setSelectedId] = useState(weaknessId);
  const [expectedVersion, setExpectedVersion] = useState(weaknessVersion);
  const [page, setPage] = useState(1);
  const [recoveryKey, setRecoveryKey] = useState("");
  const [boundExpectedVersion, setBoundExpectedVersion] = useState<number | undefined>();
  const signatures = useRef(new Map<string, string>());
  const profile = useQuery(userProfileQueryOptions());
  const history = useQuery(explanationListOptions(page));
  const weaknesses = useQuery(
    weaknessListOptions({ decision: "confirmed", page: 1, page_size: 100 }),
  );
  const selected = useQuery(weaknessOptions(selectedId));
  const bound = useQuery(explanationOptions(selected.data?.explanation_id ?? ""));
  const create = useMutation(createExplanationOptions());
  const regenerate = useMutation(regenerateExplanationOptions());
  const lookup = useQuery(knowledgeLookupOptions(recoveryKey));
  const owner = profile.data?.username ?? "";
  useEffect(() => {
    if (!owner) return;
    setRecoveryKey(readKnowledgeRequest(sessionStorage, owner, ""));
  }, [owner]);
  useEffect(() => {
    if (!lookup.data) return;
    if (owner) {
      writeKnowledgeRequest(sessionStorage, owner, "", "");
    }
    setRecoveryKey("");
    router.replace(`/learning/explanation/${lookup.data.explanation_id}?run=${lookup.data.id}`);
  }, [lookup.data, owner, router]);
  const stale = Boolean(
    selected.data && expectedVersion !== undefined && selected.data.version !== expectedVersion,
  );
  async function submit(config: ExplanationConfig) {
    if (selected.data?.explanation_id && !bound.data) return;
    const binding = selected.data?.explanation_id;
    const version = boundExpectedVersion ?? bound.data?.version;
    if (binding && version) setBoundExpectedVersion(version);
    const body = {
      ...config,
      ...(selected.data
        ? {
            weakness_id: selected.data.id,
            weakness_version: expectedVersion ?? selected.data.version,
          }
        : {}),
    };
    const signature = JSON.stringify(
      binding
        ? { operation: "regenerate", id: binding, version, config }
        : { operation: "create", body },
    );
    let key = signatures.current.get(signature);
    if (!key) {
      key = crypto.randomUUID();
      signatures.current.set(signature, key);
    }
    writeKnowledgeRequest(sessionStorage, owner, "", key);
    try {
      const result =
        binding && version
          ? await regenerate.mutateAsync({
              id: binding,
              body: { expected_version: version, config, request_key: key },
            })
          : await create.mutateAsync({ ...body, request_key: key });
      writeKnowledgeRequest(sessionStorage, owner, "", "");
      setRecoveryKey("");
      await client.invalidateQueries({ queryKey: learningAssetKeys.all });
      router.push(`/learning/explanation/${result.data.explanation.id}?run=${result.data.run.id}`);
    } catch (error) {
      if (error instanceof ApiError && (error.status ?? 0) >= 400) {
        writeKnowledgeRequest(sessionStorage, owner, "", "");
        setRecoveryKey("");
      } else setRecoveryKey(key);
    }
  }
  const draftKey = [...learningAssetKeys.all, "draft", owner, selectedId];
  const storedDraft = client.getQueryData<ExplanationConfig>(draftKey);
  const initial =
    storedDraft ??
    (selected.data
      ? {
          topic: selected.data.title,
          source_mode: selected.data.source_mode,
          knowledge_base_id: selected.data.knowledge_base_id,
          file_ids: selected.data.file_ids,
          foundation: "know_concept" as const,
          depth: "systematic" as const,
        }
      : undefined);
  return (
    <AssetLayout>
      <header className="mb-[22px]">
        <h1 className="text-2xl font-bold">学习室 · 知识精讲</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          告诉 AI 你的知识点和当前基础，获得结构化讲解。
        </p>
      </header>
      <ExplanationModes />
      {selectedId && selected.isPending ? (
        <p role="status" className="py-8 text-sm">
          正在读取活动难点…
        </p>
      ) : selected.error ? (
        <div className="space-y-3 py-5">
          <p role="alert" className="text-sm text-danger">
            {selected.error.message}
          </p>
          <Button
            variant="outline"
            onClick={() => {
              void selected.refetch();
            }}
          >
            重新读取
          </Button>
        </div>
      ) : (
        <>
          <ExplanationForm
            key={`${owner}:${selectedId}:${selected.data?.id ?? "direct"}`}
            initial={initial}
            selectedWeakness={selected.data}
            weaknesses={weaknesses.data?.data}
            pending={
              create.isPending ||
              regenerate.isPending ||
              Boolean(selected.data?.explanation_id && !bound.data) ||
              stale ||
              Boolean(selected.data && selected.data.decision !== "confirmed")
            }
            error={
              create.error?.message ??
              regenerate.error?.message ??
              bound.error?.message ??
              weaknesses.error?.message
            }
            onWeaknessChange={(id) => {
              setSelectedId(id);
              setExpectedVersion(undefined);
              create.reset();
              regenerate.reset();
              setBoundExpectedVersion(undefined);
            }}
            onDraftChange={(config) => client.setQueryData(draftKey, config)}
            onSubmit={(config) => {
              void submit(config);
            }}
          />
          {regenerate.error && selected.data?.explanation_id ? (
            <Button
              className="mt-3"
              variant="outline"
              onClick={() => {
                void bound.refetch().then((result) => {
                  if (result.data) setBoundExpectedVersion(result.data.version);
                });
              }}
            >
              读取最新精讲版本并保留输入
            </Button>
          ) : null}
          {stale ? (
            <div className="mt-4 space-y-2">
              <p role="alert" className="text-sm text-danger">
                难点版本已改变，当前输入保留，请读取最新版本后再确认。
              </p>
              <Button variant="outline" onClick={() => setExpectedVersion(selected.data?.version)}>
                使用当前版本
              </Button>
            </div>
          ) : null}
          {selected.data && selected.data.decision !== "confirmed" ? (
            <p role="alert" className="mt-4 text-sm text-danger">
              所选难点尚未确认或已撤销，请先在难点详情处理。
            </p>
          ) : null}
        </>
      )}
      {recoveryKey && lookup.isPending ? (
        <p role="status" className="mt-3 text-xs">
          正在恢复已提交的精讲任务…
        </p>
      ) : null}
      <section className="mt-8 border-t border-border pt-5">
        <h2 className="text-base font-bold">我的精讲历史</h2>
        {history.isPending ? (
          <p role="status" className="py-5 text-sm">
            正在读取历史…
          </p>
        ) : history.error ? (
          <p role="alert" className="py-5 text-sm text-danger">
            {history.error.message}
          </p>
        ) : history.data?.data.length ? (
          <ul className="mt-3 divide-y divide-border">
            {history.data.data.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <Link
                  href={`/learning/explanation/${item.id}`}
                  className="min-w-0 break-words text-sm font-semibold hover:underline"
                >
                  {item.topic}
                </Link>
                <span className="text-xs text-muted-foreground">
                  {item.config.source_mode === "materials" ? "资料模式" : "通用模式"} ·{" "}
                  {item.active_card_version
                    ? `卡片版本 ${item.active_card_version}`
                    : "尚无已发布卡片"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <AssetEmpty title="暂无精讲历史">输入知识点后开始首次文字精讲。</AssetEmpty>
        )}
        {history.data && history.data.meta.total_pages > 1 ? (
          <nav aria-label="精讲历史分页" className="mt-3 flex justify-end gap-3">
            <Button
              size="sm"
              variant="outline"
              disabled={page <= 1}
              onClick={() => setPage((old) => old - 1)}
            >
              上一页
            </Button>
            <span className="self-center text-xs">
              {page} / {history.data.meta.total_pages}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={page >= history.data.meta.total_pages}
              onClick={() => setPage((old) => old + 1)}
            >
              下一页
            </Button>
          </nav>
        ) : null}
      </section>
    </AssetLayout>
  );
}
