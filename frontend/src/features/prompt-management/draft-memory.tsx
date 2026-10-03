"use client";
import { createContext, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";

import { useAuth } from "@/features/auth/auth-provider";

export type EditorForm = {
  content: string;
  variables: string;
  dependencies: string;
  change: string;
};
export type DraftMemory = {
  definitionId: string;
  form: EditorForm;
  saved: EditorForm;
  revision: number;
  savedHash: string;
};
type MemoryScope = {
  read: (id: string) => DraftMemory | undefined;
  selected: (definitionId: string) => string | undefined;
  write: (id: string, value: DraftMemory) => void;
  remove: (id: string) => void;
};
const emptyScope: MemoryScope = {
  read: () => undefined,
  selected: () => undefined,
  write: () => undefined,
  remove: () => undefined,
};
const Context = createContext<MemoryScope>(emptyScope);

/** 位于AdminRoute内部：后台历史跳转可恢复输入；离开后台、登出或角色失效立即销毁。 */
export function PromptDraftScope({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();
  if (status !== "authenticated" || user?.role !== "admin") return null;
  // 即使管理员A直接换成管理员B、外层guard始终有效，key也会先创建空范围。
  return <AuthenticatedDraftScope key={user.id}>{children}</AuthenticatedDraftScope>;
}

function AuthenticatedDraftScope({ children }: { children: ReactNode }) {
  const drafts = useRef(new Map<string, DraftMemory>());
  const memory = useMemo<MemoryScope>(
    () => ({
      read: (id) => drafts.current.get(id),
      selected: (definitionId) =>
        [...drafts.current.entries()].findLast(
          ([, value]) => value.definitionId === definitionId,
        )?.[0],
      write: (id, value) => drafts.current.set(id, value),
      remove: (id) => {
        drafts.current.delete(id);
      },
    }),
    [],
  );
  useEffect(() => {
    const current = drafts.current;
    return () => current.clear();
  }, []);
  return <Context.Provider value={memory}>{children}</Context.Provider>;
}

export function usePromptDraftMemory() {
  return useContext(Context);
}
