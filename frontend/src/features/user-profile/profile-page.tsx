"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Camera,
  CircleAlert,
  LoaderCircle,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { toApiError, toFieldErrors } from "@/lib/api/errors";

import { ContentShell } from "@/features/file-management/content-shell";
import {
  formToPatch,
  profileToForm,
  validateProfileForm,
  type ProfileFormValues,
} from "./profile-form";
import {
  deleteAvatarMutationOptions,
  updateUserProfileMutationOptions,
  uploadAvatarMutationOptions,
  userAvatarQueryOptions,
  userProfileQueryOptions,
} from "./queries";
import { TagField } from "./tag-field";

const levelLabels = {
  intern: "实习",
  junior: "初级",
  intermediate: "中级",
  senior: "高级",
  expert: "专家",
} as const;

function useObjectUrl(blob: Blob | undefined) {
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    if (!blob) {
      setUrl(undefined);
      return;
    }
    const next = URL.createObjectURL(blob);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [blob]);
  return url;
}

export function UserProfilePage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const profileQuery = useQuery(userProfileQueryOptions());
  const profile = profileQuery.data;
  const avatarQuery = useQuery(
    userAvatarQueryOptions(profile?.version ?? 0, Boolean(profile?.avatar_set)),
  );
  const avatarUrl = useObjectUrl(avatarQuery.data);
  const updateMutation = useMutation(updateUserProfileMutationOptions(queryClient));
  const uploadMutation = useMutation(uploadAvatarMutationOptions(queryClient));
  const deleteMutation = useMutation(deleteAvatarMutationOptions(queryClient));
  const [form, setForm] = useState<ProfileFormValues | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [versionConflict, setVersionConflict] = useState(false);
  const busy = updateMutation.isPending || uploadMutation.isPending || deleteMutation.isPending;

  useEffect(() => {
    if (profile) setForm(profileToForm(profile));
  }, [profile]);

  function setField<K extends keyof ProfileFormValues>(key: K, value: ProfileFormValues[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
    setErrors((current) => ({ ...current, [key]: "", experience: "" }));
  }

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    if (!profile || !form) return;
    const localErrors = validateProfileForm(form);
    if (Object.keys(localErrors).length > 0) {
      setErrors(localErrors);
      return;
    }
    try {
      const result = await updateMutation.mutateAsync(formToPatch(form, profile.version));
      setForm(profileToForm(result.data));
      setErrors({});
      setVersionConflict(false);
    } catch (error) {
      const apiError = toApiError(error);
      if (apiError.errorKey === "PROFILE_VERSION_CONFLICT") {
        setVersionConflict(true);
        toast.error("资料已在其他位置更新，请重新加载后再修改");
      } else {
        setErrors(toFieldErrors(error));
        toast.error(apiError.message);
      }
    }
  }

  async function selectAvatar(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !profile) return;
    try {
      await uploadMutation.mutateAsync({ file, profileVersion: profile.version });
      toast.success("头像已更新");
    } catch (error) {
      const apiError = toApiError(error);
      toast.error(
        apiError.errorKey === "PROFILE_VERSION_CONFLICT"
          ? "资料版本已变化，请重新加载后上传"
          : apiError.message,
      );
    }
  }

  async function removeAvatar() {
    if (!profile) return;
    try {
      await deleteMutation.mutateAsync(profile.version);
    } catch (error) {
      toast.error(toApiError(error).message);
    }
  }

  if (profileQuery.isPending || (!form && !profileQuery.isError)) {
    return (
      <ContentShell>
        <div className="grid min-h-[60dvh] place-items-center text-xs text-muted-foreground">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          <span className="sr-only">正在加载个人资料</span>
        </div>
      </ContentShell>
    );
  }

  if (profileQuery.isError || !profile || !form) {
    return (
      <ContentShell>
        <div className="mx-auto max-w-xl px-6 py-20 text-center">
          <CircleAlert className="mx-auto size-8 text-destructive" aria-hidden="true" />
          <h1 className="mt-4 text-xl font-semibold">个人资料加载失败</h1>
          <p className="mt-2 text-xs text-muted-foreground">
            {toApiError(profileQuery.error).message}
          </p>
          <Button className="mt-6" variant="outline" onClick={() => profileQuery.refetch()}>
            <RefreshCw aria-hidden="true" />
            重新加载
          </Button>
        </div>
      </ContentShell>
    );
  }

  const avatarInitial = (profile.nickname || profile.username).slice(0, 1).toUpperCase();

  return (
    <ContentShell>
      <div className="mx-auto grid max-w-[1440px] gap-6 px-5 py-7 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-10 lg:px-[120px]">
        <aside aria-label="个人设置" className="space-y-4">
          <h1 className="text-xl font-semibold">个人设置</h1>
          <nav className="grid gap-2 text-xs" aria-label="设置导航">
            <span aria-current="page" className="rounded bg-muted px-3 py-2">
              个人资料与偏好
            </span>
            <button
              type="button"
              disabled
              title="修改密码尚未开放"
              className="px-3 py-2 text-left text-muted-foreground"
            >
              修改密码 · 尚未开放
            </button>
            <button
              type="button"
              disabled
              title="删除账号尚未开放"
              className="px-3 py-2 text-left text-muted-foreground"
            >
              删除账号 · 尚未开放
            </button>
          </nav>
        </aside>
        <form className="min-w-0" onSubmit={saveProfile} noValidate>
          <h2 className="mb-5 text-[22px] font-semibold">个人资料与默认偏好</h2>
          <section className="mb-5 border-b border-border pb-5" aria-label="头像与账户">
            <div className="flex items-center gap-4 ">
              <div className="relative grid size-14 shrink-0 place-items-center overflow-hidden rounded-full border border-surface bg-primary text-xl font-semibold text-primary-foreground shadow-sm">
                {avatarUrl ? (
                  <img src={avatarUrl} alt="当前头像" className="size-full object-cover" />
                ) : (
                  avatarInitial
                )}
                {uploadMutation.isPending && (
                  <span className="absolute inset-0 grid place-items-center bg-foreground/60 text-background">
                    <LoaderCircle className="size-6 animate-spin" aria-hidden="true" />
                    <span className="sr-only">头像处理中</span>
                  </span>
                )}
              </div>
              <div className="min-w-0">
                <p className="truncate text-lg font-semibold">{profile.nickname}</p>
                <p className="truncate text-xs text-muted-foreground">@{profile.username}</p>
                {profile.experience_display && (
                  <p className="mt-2 text-xs text-muted-foreground">{profile.experience_display}</p>
                )}
              </div>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              className="sr-only"
              accept="image/jpeg,image/png,image/webp"
              aria-label="选择头像图片"
              onChange={selectAvatar}
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => fileInputRef.current?.click()}
              >
                <Camera aria-hidden="true" />
                {profile.avatar_set ? "更换头像" : "上传头像"}
              </Button>
              {profile.avatar_set && (
                <Button type="button" variant="ghost" disabled={busy} onClick={removeAvatar}>
                  <Trash2 aria-hidden="true" />
                  删除头像
                </Button>
              )}
            </div>
            <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
              支持 JPEG、PNG、WebP，最大 5 MB。处理失败时保留当前头像。
            </p>
            <div className="mt-3">
              <div className="flex items-start gap-2.5 text-xs leading-5 text-muted-foreground">
                <ShieldCheck
                  className="mt-0.5 size-4 shrink-0 text-accent-foreground"
                  aria-hidden="true"
                />
                资料仅用于你的学习与面试个性化，不会展示在管理员业务页面。
              </div>
            </div>
          </section>
          {versionConflict && (
            <div className="flex flex-col gap-3 border-b border-amber-300 bg-amber-50 px-6 py-4 text-sm text-amber-950 sm:flex-row sm:items-center sm:justify-between sm:px-8">
              <div>
                <p className="font-medium">资料已在其他位置更新</p>
                <p className="mt-1 text-xs text-amber-800">
                  重新加载最新版本后再继续修改，避免覆盖新的内容。
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={async () => {
                  const result = await profileQuery.refetch();
                  if (result.data) setForm(profileToForm(result.data));
                  setVersionConflict(false);
                  setErrors({});
                }}
              >
                <RefreshCw aria-hidden="true" />
                重新加载最新资料
              </Button>
            </div>
          )}
          <section className="mb-6">
            <h2 className="text-sm font-semibold">基本信息</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              完善身份与目标岗位，帮助系统理解你的求职方向。
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="username">用户名</Label>
                <Input id="username" value={profile.username} readOnly disabled />
                <p className="text-xs text-muted-foreground">用户名是登录标识，暂不支持修改。</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="nickname">昵称</Label>
                <Input
                  id="nickname"
                  value={form.nickname}
                  maxLength={40}
                  aria-invalid={Boolean(errors.nickname)}
                  disabled={busy}
                  onChange={(event) => setField("nickname", event.target.value)}
                />
                {errors.nickname && <p className="text-xs text-destructive">{errors.nickname}</p>}
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="target-job">目标岗位</Label>
                <Input
                  id="target-job"
                  value={form.targetJob}
                  maxLength={120}
                  placeholder="例如：Java 后端工程师"
                  disabled={busy}
                  onChange={(event) => setField("targetJob", event.target.value)}
                />
              </div>
            </div>
          </section>

          <section className="mb-6">
            <h2 className="text-sm font-semibold">职业阶段</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>工作经验</Label>
                <div className="grid grid-cols-2 gap-3">
                  <label className="relative">
                    <Input
                      aria-label="工作经验年数"
                      inputMode="numeric"
                      value={form.experienceYears}
                      disabled={busy}
                      onChange={(event) => setField("experienceYears", event.target.value)}
                      className="pr-9"
                    />
                    <span className="absolute top-2 right-3 text-xs text-muted-foreground">年</span>
                  </label>
                  <label className="relative">
                    <Input
                      aria-label="工作经验月数"
                      inputMode="numeric"
                      value={form.experienceRemainderMonths}
                      disabled={busy}
                      onChange={(event) =>
                        setField("experienceRemainderMonths", event.target.value)
                      }
                      className="pr-9"
                    />
                    <span className="absolute top-2 right-3 text-xs text-muted-foreground">月</span>
                  </label>
                </div>
                {errors.experience && (
                  <p className="text-xs text-destructive">{errors.experience}</p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="target-level">岗位等级</Label>
                <Select
                  value={form.targetLevel || "unset"}
                  disabled={busy}
                  onValueChange={(value) =>
                    setField(
                      "targetLevel",
                      value === "unset" ? "" : (value as ProfileFormValues["targetLevel"]),
                    )
                  }
                >
                  <SelectTrigger id="target-level">
                    <SelectValue placeholder="请选择岗位等级" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="unset">暂不设置</SelectItem>
                    {Object.entries(levelLabels).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="sm:col-span-2">
                <TagField
                  id="target-skills"
                  label="目标技能"
                  description="按 Enter、逗号或“添加”生成标签，最多 30 项。"
                  placeholder="例如：Spring Boot"
                  value={form.targetSkills}
                  maxLength={50}
                  disabled={busy}
                  onChange={(value) => setField("targetSkills", value)}
                />
              </div>
            </div>
          </section>

          <section className="mb-6">
            <h2 className="text-sm font-semibold">学习偏好</h2>
            <div className="mt-3 grid gap-3">
              <TagField
                id="focus-topics"
                label="重点关注知识点"
                description="记录准备面试时希望重点强化的知识领域。"
                placeholder="例如：JVM 调优"
                value={form.focusTopics}
                maxLength={80}
                disabled={busy}
                onChange={(value) => setField("focusTopics", value)}
              />
              <div className="space-y-2">
                <Label htmlFor="learning-goal">学习目标</Label>
                <Textarea
                  id="learning-goal"
                  value={form.learningGoal}
                  maxLength={1000}
                  rows={5}
                  placeholder="例如：三个月内完成 Java 高级工程师面试准备……"
                  disabled={busy}
                  onChange={(event) => setField("learningGoal", event.target.value)}
                />
                <p className="text-right text-xs text-muted-foreground">
                  {form.learningGoal.length}/1000
                </p>
              </div>
              <div className="max-w-sm space-y-2">
                <Label htmlFor="preferred-language">默认语言</Label>
                <Select
                  value={form.preferredLanguage}
                  disabled={busy}
                  onValueChange={(value) =>
                    setField("preferredLanguage", value as ProfileFormValues["preferredLanguage"])
                  }
                >
                  <SelectTrigger id="preferred-language">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="zh-CN">简体中文</SelectItem>
                    <SelectItem value="en-US">English</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </section>

          <section className="mb-6">
            <h2 className="text-sm font-semibold">活动薄弱点</h2>
            {profile.active_weaknesses.length === 0 ? (
              <div className="mt-4 border-l-2 border-border py-2 pl-3">
                <p className="text-sm font-medium">还没有可用的薄弱点证据</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  完成练习或模拟面试后，系统会在这里汇总近期需要强化的知识点；该区域只读，不需要手工维护。
                </p>
              </div>
            ) : (
              <ul className="mt-4 grid gap-3">
                {profile.active_weaknesses.map((item) => (
                  <li key={item.id} className="rounded-md border border-border px-4 py-3">
                    <p className="text-sm font-medium">{item.name}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{item.source_summary}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <footer className="flex items-center justify-between gap-4 border-t border-border bg-background py-4">
            <p className="text-xs text-muted-foreground">资料版本 {profile.version}</p>
            <Button type="submit" variant="brand" disabled={busy}>
              {updateMutation.isPending ? (
                <LoaderCircle className="animate-spin" aria-hidden="true" />
              ) : (
                <Save aria-hidden="true" />
              )}
              {updateMutation.isPending ? "保存中…" : "保存资料"}
            </Button>
          </footer>
        </form>
      </div>
    </ContentShell>
  );
}
