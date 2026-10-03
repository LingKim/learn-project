"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { AnswerContent } from "@/features/learning/answer-content";
import type { KnowledgeCardView } from "./api";
import { sectionLabels } from "./asset-layout";

export function CardContent({ card }: { card: KnowledgeCardView }) {
  const [hints, setHints] = useState(false);
  return (
    <div className="mt-[18px] grid min-w-0 gap-7 lg:grid-cols-[220px_minmax(0,1fr)]">
      <nav aria-label="本次讲解目录" className="flex flex-wrap content-start gap-1 lg:flex-col">
        <h2 className="w-full py-2 text-sm font-semibold">本次讲解</h2>
        {sectionLabels.map((title, index) => (
          <a
            key={title}
            href={`#card-section-${index}`}
            className="flex gap-2 rounded-md px-2.5 py-2 text-xs text-muted-foreground hover:bg-muted"
          >
            <span>0{index + 1}</span>
            {title}
          </a>
        ))}
      </nav>
      <div className="min-w-0 space-y-[14px]">
        <Section index={0}>
          <AnswerContent content={card.concept} />
          <ul className="mt-2 list-disc space-y-2 pl-5 text-sm">
            {card.applications.map((text, index) => (
              <li key={index}>{text}</li>
            ))}
          </ul>
        </Section>
        <Section index={1}>
          <ul className="list-disc space-y-3 pl-5 text-sm">
            {card.principles.map((text, index) => (
              <li key={index}>
                <AnswerContent content={text} />
              </li>
            ))}
          </ul>
        </Section>
        <Section index={2}>
          {card.examples.map((example, index) => (
            <article key={index} className="py-2">
              <h3 className="text-sm font-semibold">{example.title}</h3>
              <AnswerContent content={example.content} />
            </article>
          ))}
        </Section>
        <Section index={3}>
          <ul className="list-disc space-y-3 pl-5 text-sm">
            {card.misconceptions.map((text, index) => (
              <li key={index}>
                <AnswerContent content={text} />
              </li>
            ))}
          </ul>
        </Section>
        <Section index={4}>
          {card.exercises.map((exercise, index) => (
            <article key={index} className="py-2">
              <AnswerContent content={exercise.question} />
              {hints ? (
                <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-muted-foreground">
                  {exercise.self_check_points.map((point, pointIndex) => (
                    <li key={pointIndex}>{point}</li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))}
          <Button
            variant="outline"
            size="sm"
            type="button"
            aria-expanded={hints}
            onClick={() => setHints((old) => !old)}
          >
            {hints ? "收起自查要点" : "查看自查要点"}
          </Button>
        </Section>
      </div>
    </div>
  );
}

function Section({ index, children }: { index: number; children: ReactNode }) {
  return (
    <section
      id={`card-section-${index}`}
      className="flex min-w-0 scroll-mt-5 gap-[14px] rounded-lg border border-border bg-surface px-4 py-[13px]"
    >
      <span className="grid size-[30px] shrink-0 place-items-center rounded-md bg-muted text-xs text-accent-foreground">
        0{index + 1}
      </span>
      <div className="min-w-0 flex-1">
        <h2 className="mb-2 text-sm font-semibold">{sectionLabels[index]}</h2>
        <div className="min-w-0 text-sm leading-7">{children}</div>
      </div>
    </section>
  );
}
