import { describe, expect, it } from "vitest";

import type { UserProfileView } from "./api";
import { formToPatch, profileToForm, validateProfileForm } from "./profile-form";

const profile: UserProfileView = {
  username: "lilin",
  nickname: "李老板",
  target_job: "Java 后端工程师",
  experience_months: 38,
  experience_display: "3 年 2 个月",
  target_level: "senior",
  target_skills: ["Java", "Spring Boot"],
  focus_topics: ["JVM"],
  learning_goal: "完成面试准备",
  preferred_language: "zh-CN",
  avatar_set: false,
  avatar_url: null,
  version: 4,
  active_weaknesses: [],
};

describe("个人资料表单转换", () => {
  it("把后端总月数拆成年月，并在提交时无损还原", () => {
    const form = profileToForm(profile);
    expect(form.experienceYears).toBe("3");
    expect(form.experienceRemainderMonths).toBe("2");
    expect(formToPatch(form, profile.version)).toMatchObject({
      version: 4,
      experience_months: 38,
      target_skills: ["Java", "Spring Boot"],
    });
  });

  it("保留空经验为 null，而不是错误地提交 0 个月", () => {
    const form = profileToForm({ ...profile, experience_months: null });
    expect(formToPatch(form, 4).experience_months).toBeNull();
  });

  it("在请求前拦截空昵称和非法月份", () => {
    const form = profileToForm(profile);
    expect(
      validateProfileForm({
        ...form,
        nickname: " ",
        experienceRemainderMonths: "12",
      }),
    ).toEqual({ nickname: "请输入昵称", experience: "月份应为 0–11" });
  });
});
