import {
  authLogin,
  authLogout,
  authMe,
  authRefresh,
  authRegister,
} from "@/lib/api/generated/sdk.gen";
import type {
  AuthPayload,
  LoginRequest,
  RegisterRequest,
  UserView,
} from "@/lib/api/generated/types.gen";
import {
  API_BASE_URL,
  requestMutation,
  requestQueryData,
  type MutationResult,
} from "@/lib/api/protocol";

const sharedOptions = {
  baseUrl: API_BASE_URL,
  credentials: "include" as const,
  throwOnError: true as const,
};

export type { AuthPayload, LoginRequest, RegisterRequest, UserView };

export function registerAccount(body: RegisterRequest): Promise<MutationResult<AuthPayload>> {
  return requestMutation(() => authRegister({ ...sharedOptions, body }));
}

export function loginAccount(body: LoginRequest): Promise<MutationResult<AuthPayload>> {
  return requestMutation(() => authLogin({ ...sharedOptions, body }));
}

export function refreshSession(): Promise<MutationResult<AuthPayload>> {
  return requestMutation(() => authRefresh(sharedOptions));
}

export function getCurrentUser(accessToken: string): Promise<UserView> {
  return requestQueryData(() =>
    authMe({
      ...sharedOptions,
      headers: { Authorization: `Bearer ${accessToken}` },
    }),
  );
}

export function logoutSession(accessToken: string | null): Promise<MutationResult<null>> {
  return requestMutation(() =>
    authLogout({
      ...sharedOptions,
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
    }),
  );
}
