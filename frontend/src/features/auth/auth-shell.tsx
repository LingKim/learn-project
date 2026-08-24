import { BookOpenText, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

interface AuthShellProps {
  children: ReactNode;
  eyebrow: string;
  title: string;
  description: string;
  compact?: boolean;
}

export function AuthShell({
  children,
  eyebrow,
  title,
  description,
  compact = false,
}: AuthShellProps) {
  return (
    <main className="min-h-dvh bg-background lg:grid lg:grid-cols-[minmax(19rem,0.82fr)_minmax(32rem,1.18fr)]">
      <section className="relative hidden min-h-dvh flex-col justify-between overflow-hidden bg-sidebar px-12 py-10 lg:flex xl:px-16 xl:py-12">
        <div className="relative z-10 flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-md bg-primary text-primary-foreground">
            <BookOpenText aria-hidden="true" className="size-5" strokeWidth={2.2} />
          </span>
          <span className="text-lg font-semibold tracking-[-0.025em]">学面通AI</span>
        </div>

        <div className="relative z-10 max-w-[31rem]">
          <p className="text-xs font-semibold tracking-[0.18em] text-accent-foreground uppercase">
            {eyebrow}
          </p>
          <h1 className="mt-6 text-[clamp(2.65rem,4.2vw,4.8rem)] leading-[1.02] font-semibold tracking-[-0.06em] text-foreground">
            {title}
          </h1>
          <p className="mt-6 max-w-[28rem] text-base leading-7 text-muted-foreground">
            {description}
          </p>
        </div>

        <div className="relative z-10 flex items-center gap-2 text-xs text-muted-foreground">
          <ShieldCheck aria-hidden="true" className="size-4 text-accent-foreground" />
          学习记录仅用于优化你的学习体验
        </div>

        <div
          className="pointer-events-none absolute top-[18%] right-[-3rem] grid rotate-6 grid-cols-6 gap-3 opacity-45"
          aria-hidden="true"
        >
          {Array.from({ length: 30 }, (_, index) => (
            <span key={index} className="size-1 rounded-full bg-primary" />
          ))}
        </div>
      </section>

      <section className="flex min-h-dvh items-center px-5 py-8 sm:px-8 lg:px-12 xl:px-20">
        <div className={compact ? "mx-auto w-full max-w-[31rem]" : "mx-auto w-full max-w-[34rem]"}>
          <div className="mb-12 flex items-center gap-3 lg:hidden">
            <span className="grid size-9 place-items-center rounded-md bg-primary text-primary-foreground">
              <BookOpenText aria-hidden="true" className="size-[1.125rem]" strokeWidth={2.2} />
            </span>
            <span className="font-semibold tracking-[-0.02em]">学面通AI</span>
          </div>
          {children}
        </div>
      </section>
    </main>
  );
}
