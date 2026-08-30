import type { UserProfilePatch, UserProfileView } from "./api";

export type ProfileFormValues = {
  nickname: string;
  targetJob: string;
  experienceYears: string;
  experienceRemainderMonths: string;
  targetLevel: NonNullable<UserProfilePatch["target_level"]> | "";
  targetSkills: string[];
  focusTopics: string[];
  learningGoal: string;
  preferredLanguage: NonNullable<UserProfilePatch["preferred_language"]>;
};

export function profileToForm(profile: UserProfileView): ProfileFormValues {
  const total = profile.experience_months;
  return {
    nickname: profile.nickname,
    targetJob: profile.target_job ?? "",
    experienceYears: total === null ? "" : String(Math.floor(total / 12)),
    experienceRemainderMonths: total === null ? "" : String(total % 12),
    targetLevel: profile.target_level ?? "",
    targetSkills: profile.target_skills ?? [],
    focusTopics: profile.focus_topics ?? [],
    learningGoal: profile.learning_goal ?? "",
    preferredLanguage: profile.preferred_language ?? "zh-CN",
  };
}

function optionalText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

export function formToPatch(values: ProfileFormValues, version: number): UserProfilePatch {
  const hasExperience = values.experienceYears !== "" || values.experienceRemainderMonths !== "";
  const years = Number(values.experienceYears || 0);
  const months = Number(values.experienceRemainderMonths || 0);
  return {
    version,
    nickname: values.nickname.trim(),
    target_job: optionalText(values.targetJob),
    experience_months: hasExperience ? years * 12 + months : null,
    target_level: values.targetLevel || null,
    target_skills: values.targetSkills,
    focus_topics: values.focusTopics,
    learning_goal: optionalText(values.learningGoal),
    preferred_language: values.preferredLanguage,
  };
}

export function validateProfileForm(values: ProfileFormValues): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!values.nickname.trim()) errors.nickname = "请输入昵称";
  if (values.nickname.trim().length > 40) errors.nickname = "昵称最多 40 个字符";
  const years = Number(values.experienceYears || 0);
  const months = Number(values.experienceRemainderMonths || 0);
  if (!Number.isInteger(years) || years < 0 || years > 60) errors.experience = "年份应为 0–60";
  if (!Number.isInteger(months) || months < 0 || months > 11) errors.experience = "月份应为 0–11";
  return errors;
}
