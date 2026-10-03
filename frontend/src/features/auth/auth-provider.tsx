"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { toApiError } from "@/lib/api/errors";

import type { AuthPayload, UserView } from "./api";
import { getCurrentUser, logoutSession, refreshSession } from "./api";

type AuthStatus = "loading" | "authenticated" | "anonymous";

type AuthContextValue = {
  status: AuthStatus;
  user: UserView | null;
  completeAuthentication: (payload: AuthPayload, rememberedUsername?: string) => void;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const REMEMBERED_USERNAME_KEY = "auth:remembered-username:v1";

let accessToken: string | null = null;
let accessTokenExpiresAt = 0;
let initializationPromise: Promise<UserView | null> | null = null;
let refreshPromise: Promise<AuthPayload> | null = null;

function setAccessToken(token: string | null, expiresIn = 0) {
  accessToken = token;
  accessTokenExpiresAt = token ? Date.now() + expiresIn * 1000 : 0;
}

async function refreshSingleFlight(): Promise<AuthPayload> {
  if (!refreshPromise) {
    refreshPromise = refreshSession()
      .then((result) => {
        setAccessToken(result.data.access_token, result.data.expires_in);
        return result.data;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

function initializeAuthentication(): Promise<UserView | null> {
  if (!initializationPromise) {
    initializationPromise = refreshSingleFlight()
      .then((payload) => getCurrentUser(payload.access_token))
      .catch(() => {
        setAccessToken(null);
        return null;
      });
  }
  return initializationPromise;
}

function saveRememberedUsername(username?: string) {
  try {
    if (username) localStorage.setItem(REMEMBERED_USERNAME_KEY, username);
    else localStorage.removeItem(REMEMBERED_USERNAME_KEY);
  } catch {
    // Safari 隐私模式或禁用存储时，认证本身仍应正常工作。
  }
}

export function loadRememberedUsername(): string {
  try {
    return localStorage.getItem(REMEMBERED_USERNAME_KEY) ?? "";
  } catch {
    return "";
  }
}

export async function authenticatedAccessToken(): Promise<string> {
  if (accessToken && Date.now() < accessTokenExpiresAt - 30_000) return accessToken;
  return (await refreshSingleFlight()).access_token;
}

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  const router = useRouter();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<UserView | null>(null);

  useEffect(() => {
    let active = true;
    void initializeAuthentication().then((restoredUser) => {
      if (!active) return;
      setUser(restoredUser);
      setStatus(restoredUser ? "authenticated" : "anonymous");
    });
    return () => {
      active = false;
    };
  }, []);

  const completeAuthentication = useCallback(
    (payload: AuthPayload, rememberedUsername?: string) => {
      setAccessToken(payload.access_token, payload.expires_in);
      setUser(payload.user);
      setStatus("authenticated");
      saveRememberedUsername(rememberedUsername);
      router.replace("/");
    },
    [router],
  );

  const logout = useCallback(async () => {
    try {
      await logoutSession(accessToken);
    } catch (error) {
      const apiError = toApiError(error);
      if (apiError.status !== 401) throw apiError;
    } finally {
      setAccessToken(null);
      setUser(null);
      setStatus("anonymous");
      router.replace("/login");
    }
  }, [router]);

  const value = useMemo(
    () => ({ status, user, completeAuthentication, logout }),
    [completeAuthentication, logout, status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
