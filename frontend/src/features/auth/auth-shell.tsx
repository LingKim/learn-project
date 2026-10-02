import { BookOpenText, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

interface AuthShellProps {
  children: ReactNode;
  eyebrow: string;
  title: string;
  description: string;
  compact?: boolean;
  variant?: "login" | "register";
}

export function AuthShell({ children, title, description, variant = "login" }: AuthShellProps) {
  const registering = variant === "register";
  return (
    <main
      className={`min-h-dvh bg-background lg:grid ${registering ? "lg:grid-cols-[460px_minmax(0,1fr)]" : "lg:grid-cols-[520px_minmax(0,1fr)]"}`}
    >
      <section
        className={`hidden min-h-dvh flex-col justify-between border-r border-border bg-sidebar py-[72px] lg:flex ${registering ? "px-14" : "px-16"}`}
      >
        <div className="flex items-center gap-3">
          <span className="grid size-[42px] place-items-center rounded-md bg-primary text-primary-foreground">
            <BookOpenText aria-hidden="true" className="size-5" />
          </span>
          <span className="text-[22px] font-bold">学面通AI</span>
        </div>
        <div>
          <h1 className="whitespace-pre-line text-[40px] leading-[1.25] font-semibold">
            {title.replace("，", "，\n")}
          </h1>
          <p className="mt-5 text-base leading-7 text-muted-foreground">{description}</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <ShieldCheck aria-hidden="true" className="size-4 text-success" />
          学习记录仅用于优化你的学习体验
        </div>
      </section>
      <section className="flex min-h-dvh items-center justify-center px-5 py-10 sm:px-8">
        <div className={`w-full ${registering ? "max-w-[460px]" : "max-w-[420px]"}`}>
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <BookOpenText className="size-8 text-accent-foreground" />
            <span className="font-semibold">学面通AI</span>
          </div>
          {children}
        </div>
      </section>
    </main>
  );
}
