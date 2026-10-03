"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PanelLeft, PanelTop } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
import type { UserProfileView } from "./api";
import { userProfileQueryOptions, updateUserProfileMutationOptions } from "./queries";

type NavigationPosition = UserProfileView["navigation_position"];

export function NavigationSettings({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const client = useQueryClient();
  const profile = useQuery(userProfileQueryOptions());
  const mutation = useMutation(updateUserProfileMutationOptions(client));
  const [selection, setSelection] = useState<NavigationPosition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selected = selection ?? profile.data?.navigation_position ?? "left";

  async function save() {
    if (!profile.data) return;
    setError(null);
    try {
      await mutation.mutateAsync({ version: profile.data.version, navigation_position: selected });
      onOpenChange(false);
    } catch (cause) {
      const failure = toApiError(cause);
      if (failure.status === 409) await profile.refetch();
      setError(failure.message);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[560px] bg-surface">
        <DialogHeader>
          <DialogTitle>用户设置</DialogTitle>
          <DialogDescription>设置保存到账号，跨设备同步。</DialogDescription>
        </DialogHeader>
        {profile.isError ? (
          <div role="alert">
            设置读取失败。
            <Button variant="outline" onClick={() => profile.refetch()}>
              重新加载
            </Button>
          </div>
        ) : profile.isPending ? (
          <p role="status">正在读取设置…</p>
        ) : (
          <fieldset disabled={mutation.isPending}>
            <legend className="mb-3 text-sm font-semibold">导航位置</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {(
                [
                  [
                    "left",
                    "左侧导航（默认）",
                    "仅显示图标，悬停显示名称，为会话留出更多高度。",
                    PanelLeft,
                  ],
                  ["top", "顶部导航", "紧凑横向导航，图标与文字并列。", PanelTop],
                ] as const
              ).map(([value, label, description, Icon]) => (
                <label
                  key={value}
                  className={cn(
                    "cursor-pointer rounded-lg border p-4 transition-colors motion-reduce:transition-none",
                    selected === value
                      ? "border-primary bg-muted"
                      : "border-border hover:bg-sidebar",
                  )}
                >
                  <div className="mb-3 flex items-center justify-between">
                    <Icon aria-hidden="true" className="size-6" />
                    <input
                      type="radio"
                      name="navigation-position"
                      value={value}
                      checked={selected === value}
                      onChange={() => setSelection(value)}
                      className="size-4 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2"
                    />
                  </div>
                  <span className="text-sm font-semibold">{label}</span>
                  <span className="mt-2 block text-xs leading-5 text-muted-foreground">
                    {description}
                  </span>
                </label>
              ))}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              小屏幕使用紧凑图标导航，桌面端遵循此设置。
            </p>
          </fieldset>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button
            variant="outline"
            disabled={mutation.isPending}
            onClick={() => onOpenChange(false)}
          >
            取消
          </Button>
          <Button
            variant="brand"
            disabled={!profile.data || profile.isError || mutation.isPending}
            onClick={() => void save()}
          >
            {mutation.isPending ? "正在保存…" : "保存设置"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
