"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AnswerContent } from "@/features/learning/answer-content";
import { ApiError } from "@/lib/api/errors";
import type { KnowledgeCardView } from "./api";
import { explanationSourceOptions, learningAssetKeys } from "./queries";

export function CardSources({
  card,
  sourceAvailable,
}: {
  card: KnowledgeCardView;
  sourceAvailable: boolean;
}) {
  const client = useQueryClient();
  const [sourceId, setSourceId] = useState("");
  const [unavailableMessage, setUnavailableMessage] = useState("");
  const available = sourceAvailable && card.source_available;
  const options = explanationSourceOptions(card.explanation_id, card.version, sourceId);
  const query = useQuery({ ...options, enabled: available && Boolean(sourceId) });
  useEffect(() => {
    const invalidResponse =
      query.error instanceof ApiError && [404, 409].includes(query.error.status ?? 0);
    if (available && !invalidResponse) return;
    if (invalidResponse)
      setUnavailableMessage(query.error?.message ?? "来源已失效，原文预览不可用。");
    setSourceId("");
    const queryKey = learningAssetKeys.sources(card.explanation_id, card.version);
    void client.cancelQueries({ queryKey });
    client.removeQueries({ queryKey });
  }, [available, client, card.explanation_id, card.version, query.error]);
  return (
    <section className="mt-5 border-t border-border pt-4" aria-label="知识来源">
      <h2 className="mb-2 text-sm font-semibold">知识来源</h2>
      {unavailableMessage ? (
        <p role="alert" className="mb-2 text-xs text-danger">
          {unavailableMessage}
        </p>
      ) : null}
      {card.source_mode === "general" ? (
        <p className="text-xs text-muted-foreground">模型通用知识，不引用个人资料。</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {(card.citations ?? []).map((ref) => (
            <Button
              key={ref.source_id}
              variant="outline"
              size="sm"
              disabled={!available}
              onClick={() => {
                setUnavailableMessage("");
                setSourceId(ref.source_id);
              }}
            >
              {available
                ? `${ref.display_name}${ref.page_start ? ` · 第 ${ref.page_start} 页` : ref.paragraph_start ? ` · 第 ${ref.paragraph_start} 段` : ""}`
                : "来源已失效"}
            </Button>
          ))}
        </div>
      )}
      <Dialog
        open={available && Boolean(sourceId)}
        onOpenChange={(open) => {
          if (!open) setSourceId("");
        }}
      >
        <DialogContent className="max-h-[80dvh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>资料来源</DialogTitle>
            <DialogDescription>
              {query.data?.source.display_name ?? "正在核对当前资料授权"}
            </DialogDescription>
          </DialogHeader>
          {query.isPending ? (
            <p role="status">正在读取资料…</p>
          ) : query.error ? (
            <p role="alert" className="text-sm text-danger">
              {query.error.message}
            </p>
          ) : available && query.data?.available && query.data.evidence ? (
            <AnswerContent content={query.data.evidence} />
          ) : (
            <p className="text-sm text-muted-foreground">来源已失效，原文预览不可用。</p>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
