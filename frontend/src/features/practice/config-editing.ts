import type { PracticeConfig, SetView } from "./api";

const profileFields = [
  "target_job",
  "experience_months",
  "target_level",
  "target_skills",
  "focus_topics",
  "learning_goal",
  "preferred_language",
] as const;

export function configForEditing(
  set: Pick<SetView, "config" | "profile_override_fields">,
): PracticeConfig {
  const config = { ...set.config };
  const overrides = new Set(set.profile_override_fields ?? []);
  for (const field of profileFields) {
    if (!overrides.has(field)) delete config[field];
  }
  return config;
}
