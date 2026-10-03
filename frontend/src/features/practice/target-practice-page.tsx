"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { weaknessOptions, explanationCardOptions } from "@/features/learning-assets/queries";
import { ContentShell } from "@/features/file-management/content-shell";
import type { PracticeConfig } from "./api";
import { PracticePage } from "./practice-page";

export function TargetPracticePage({
  weaknessId,
  explanationId,
  version,
}: {
  weaknessId: string;
  explanationId: string;
  version: number;
}) {
  const invalid = Boolean(weaknessId && explanationId) || !Number.isInteger(version) || version < 1;
  const weakness = useQuery({
    ...weaknessOptions(weaknessId),
    enabled: !invalid && Boolean(weaknessId),
  });
  const card = useQuery({
    ...explanationCardOptions(explanationId, version),
    enabled: !invalid && Boolean(explanationId),
  });
  const failure = weakness.error ?? card.error;
  const source = weaknessId ? weakness.data : card.data;
  const stale = Boolean(
    weakness.data && (weakness.data.version !== version || weakness.data.decision !== "confirmed"),
  );
  if (invalid || failure || stale || (source && !source.source_available)) {
    return (
      <ContentShell>
        <section className="p-6 sm:p-10">
          <h1 className="text-xl font-semibold">针对性练习</h1>
          <p role="alert" className="my-4 text-sm">
            {invalid
              ? "目标参数不完整。"
              : (failure?.message ??
                (stale ? "目标版本已变化，请重新选择。" : "目标来源已失效，请重新选择有效资料。"))}
          </p>
          <Link
            href={
              weaknessId ? `/weaknesses/${weaknessId}` : `/learning/explanation/${explanationId}`
            }
            className="underline underline-offset-4"
          >
            返回目标详情
          </Link>
        </section>
      </ContentShell>
    );
  }
  if (!source)
    return (
      <ContentShell>
        <p role="status" className="p-8">
          正在读取学习目标…
        </p>
      </ContentShell>
    );
  const topic = weakness.data?.title ?? card.data?.config.topic ?? "";
  const initial: PracticeConfig = {
    mode: "practice",
    topic,
    source_mode: source.source_mode,
    knowledge_base_id:
      weakness.data?.knowledge_base_id ?? card.data?.config.knowledge_base_id ?? null,
    file_ids: weakness.data?.file_ids ?? card.data?.config.file_ids ?? [],
    difficulty: "medium",
    question_count: 5,
    question_types: { single_choice: 5 },
    learning_target: weaknessId
      ? { kind: "weakness", id: weaknessId, version }
      : { kind: "explanation", id: explanationId, card_version: version },
  };
  return (
    <PracticePage
      key={`${weaknessId}:${explanationId}:${version}`}
      initialConfig={initial}
      initialTitle={`${topic} · 针对性练习`}
    />
  );
}
