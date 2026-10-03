"use client";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { AnswerContent } from "@/features/learning/answer-content";
import type { PracticeQuestion } from "./api";
import { practiceKeys, practiceSourceOptions } from "./queries";
export function SourceLinks({
  setId,
  revisionId,
  question,
  available,
}: {
  setId: string;
  revisionId: string;
  question: PracticeQuestion;
  available: boolean;
}) {
  const [sourceId, setSourceId] = useState("");
  const client = useQueryClient();
  const options = practiceSourceOptions(setId, revisionId, question.question_id, sourceId);
  const query = useQuery({ ...options, enabled: available && options.enabled });
  useEffect(() => {
    if (available) return;
    setSourceId("");
    const queryKey = [...practiceKeys.revision(setId, revisionId), "source", question.question_id];
    void client.cancelQueries({ queryKey });
    client.removeQueries({ queryKey });
  }, [available, client, setId, revisionId, question.question_id]);
  return (
    <div className="space-y-2">
      {question.source_refs?.length ? (
        <div className="flex flex-wrap gap-2">
          {question.source_refs.map((s) => (
            <Button
              key={s.source_id}
              variant="outline"
              size="sm"
              disabled={!available}
              onClick={() => setSourceId(s.source_id)}
            >
              {available ? s.display_name : "来源已失效"}
              {available && s.page_start
                ? ` · 第 ${s.page_start} 页`
                : available && s.paragraph_start
                  ? ` · 第 ${s.paragraph_start} 段`
                  : ""}
            </Button>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">模型通用知识</p>
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
    </div>
  );
}
