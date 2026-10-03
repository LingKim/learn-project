"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { explanationReviewOptions, weaknessReviewOptions } from "./queries";
import { reviewLabels } from "./review-labels";

export function ReviewHistory({ kind, id }: { kind: "weakness" | "explanation"; id: string }) {
  const [page, setPage] = useState(1);
  const query = useQuery(
    kind === "weakness" ? weaknessReviewOptions(id, page) : explanationReviewOptions(id, page),
  );
  return (
    <section aria-label="复习与验证记录">
      <h2 className="mb-3 text-base font-bold">复习与验证记录</h2>
      {query.isPending ? (
        <p role="status" className="text-xs">
          正在读取复习记录…
        </p>
      ) : query.error ? (
        <div className="space-y-2">
          <p role="alert" className="text-xs text-danger">
            {query.error.message}
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              void query.refetch();
            }}
          >
            重新读取
          </Button>
        </div>
      ) : query.data?.data.length ? (
        <ul className="divide-y divide-border border-y border-border">
          {query.data.data.map((review) => (
            <li key={review.id} className="space-y-2 py-3 text-xs">
              <Link
                className="font-semibold hover:underline"
                href={`/learning/practice/${review.set_id}?attempt=${review.attempt_id}&view=report`}
              >
                {new Date(review.created_at).toLocaleString("zh-CN")} · 结论版本 {review.version}
              </Link>
              <p>
                相关题 {review.total_related} · 提交 {review.submitted_count} · 评分{" "}
                {review.graded_count} · 正确 {review.correct_count} · 低置信度{" "}
                {review.low_confidence_count}
              </p>
              <p className={review.validation_passed ? "text-success" : "text-muted-foreground"}>
                {review.validation_passed
                  ? kind === "weakness"
                    ? "本次验证通过；是否标记已掌握由你决定。"
                    : "本次验证通过"
                  : (reviewLabels[review.conclusion] ?? "本次验证尚未通过。")}
              </p>
              {!review.source_available ? (
                <p className="text-muted-foreground">来源已失效，保留历史结论。</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">
          暂无针对性再练记录。{kind === "explanation" ? "直接精讲再练不会隐式创建难点。" : ""}
        </p>
      )}
      {query.data && query.data.meta.total_pages > 1 ? (
        <nav
          aria-label="复习记录分页"
          className="mt-3 flex flex-wrap items-center justify-end gap-3"
        >
          <Button
            size="sm"
            variant="outline"
            disabled={page <= 1}
            onClick={() => setPage((old) => old - 1)}
          >
            上一页
          </Button>
          <span className="text-xs">
            {page} / {query.data.meta.total_pages}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={page >= query.data.meta.total_pages}
            onClick={() => setPage((old) => old + 1)}
          >
            下一页
          </Button>
        </nav>
      ) : null}
    </section>
  );
}
