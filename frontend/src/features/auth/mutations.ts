import { mutationOptions } from "@tanstack/react-query";

import type { LoginRequest, RegisterRequest } from "./api";
import { loginAccount, logoutSession, registerAccount } from "./api";

export const authKeys = {
  all: ["auth"] as const,
  currentUser: () => [...authKeys.all, "current-user"] as const,
};

export function loginMutationOptions() {
  return mutationOptions({
    mutationKey: [...authKeys.all, "login"],
    mutationFn: (body: LoginRequest) => loginAccount(body),
    meta: { errorMode: "local", successToast: false },
  });
}

export function registerMutationOptions() {
  return mutationOptions({
    mutationKey: [...authKeys.all, "register"],
    mutationFn: (body: RegisterRequest) => registerAccount(body),
    meta: { errorMode: "local", successToast: false },
  });
}

export function logoutMutationOptions(accessToken: string | null) {
  return mutationOptions({
    mutationKey: [...authKeys.all, "logout"],
    mutationFn: () => logoutSession(accessToken),
    meta: { errorMode: "local", successToast: false },
  });
}
