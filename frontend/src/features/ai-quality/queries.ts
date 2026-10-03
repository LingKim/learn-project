import { queryOptions, mutationOptions, type QueryClient } from "@tanstack/react-query";
import * as api from "./api";
import { qualityKeys, protectQualityCache, removeQualityBody } from "./cache";
export { qualityKeys, protectQualityCache, removeQualityBody } from "./cache";

const privateQuery = { gcTime: 0, staleTime: 0, retry: false as const };
const privateMutation = {
  gcTime: 0,
  retry: false as const,
  meta: { errorMode: "global" as const },
};

export function casesQueryOptions(query: Parameters<typeof api.listCases>[0] = {}) {
  return queryOptions({
    ...privateQuery,
    queryKey: [...qualityKeys.userLists, query],
    queryFn: ({ signal }) => api.listCases(query, signal),
  });
}
export function caseQueryOptions(client: QueryClient, id: string, version: number) {
  protectQualityCache(client);
  return queryOptions({
    ...privateQuery,
    queryKey: qualityKeys.detail("user", id, version),
    queryFn: ({ signal }) => api.getCase(id, signal),
    enabled: Boolean(id),
  });
}
export function overviewQueryOptions() {
  return queryOptions({
    ...privateQuery,
    queryKey: qualityKeys.overview,
    queryFn: ({ signal }) => api.getOverview(signal),
  });
}
export function adminCasesQueryOptions(query: Parameters<typeof api.listAdminCases>[0] = {}) {
  return queryOptions({
    ...privateQuery,
    queryKey: [...qualityKeys.adminLists, query],
    queryFn: ({ signal }) => api.listAdminCases(query, signal),
  });
}
export function adminCaseQueryOptions(client: QueryClient, id: string, version: number) {
  protectQualityCache(client);
  return queryOptions({
    ...privateQuery,
    queryKey: qualityKeys.detail("admin", id, version),
    queryFn: ({ signal }) => api.getAdminCase(id, signal),
    enabled: Boolean(id),
  });
}
export function snapshotQueryOptions(
  client: QueryClient,
  id: string,
  caseVersion: number,
  query: Parameters<typeof api.getSnapshot>[1],
) {
  protectQualityCache(client);
  return queryOptions({
    ...privateQuery,
    queryKey: qualityKeys.snapshot(
      id,
      caseVersion,
      query.grant_id,
      query.expected_grant_version,
      query.fields,
    ),
    queryFn: ({ signal }) => api.getSnapshot(id, query, signal),
    enabled: Boolean(id && query.grant_id && query.fields.length),
  });
}
async function refresh(client: QueryClient) {
  await Promise.all([
    client.invalidateQueries({ queryKey: qualityKeys.userLists }),
    client.invalidateQueries({ queryKey: qualityKeys.adminLists }),
    client.invalidateQueries({ queryKey: qualityKeys.overview }),
  ]);
}
export function createCaseMutationOptions(client: QueryClient) {
  return mutationOptions({
    ...privateMutation,
    mutationKey: [...qualityKeys.all, "user", "create"],
    mutationFn: api.createCase,
    onSuccess: () => refresh(client),
  });
}

export function addMessageMutationOptions(client: QueryClient) {
  return mutationOptions({
    ...privateMutation,
    mutationKey: [...qualityKeys.all, "user", "addMessage"],
    mutationFn: (input: { id: string; body: Parameters<typeof api.addMessage>[1] }) =>
      api.addMessage(input.id, input.body),
    onMutate: (input) => removeQualityBody(client, input.id),
    onSettled: async (_data, _error, input) => {
      await removeQualityBody(client, input.id);
      await refresh(client);
    },
  });
}

export function decideGrantMutationOptions(client: QueryClient) {
  return mutationOptions({
    ...privateMutation,
    mutationKey: [...qualityKeys.all, "user", "decideGrant"],
    mutationFn: (input: {
      id: string;
      grantId: string;
      body: Parameters<typeof api.decideGrant>[2];
    }) => api.decideGrant(input.id, input.grantId, input.body),
    onMutate: (input) => removeQualityBody(client, input.id),
    onSettled: async (_data, _error, input) => {
      await removeQualityBody(client, input.id);
      await refresh(client);
    },
  });
}

export function revokeGrantMutationOptions(client: QueryClient) {
  return mutationOptions({
    ...privateMutation,
    mutationKey: [...qualityKeys.all, "user", "revokeGrant"],
    mutationFn: (input: {
      id: string;
      grantId: string;
      body: Parameters<typeof api.revokeGrant>[2];
    }) => api.revokeGrant(input.id, input.grantId, input.body),
    onMutate: (input) => removeQualityBody(client, input.id),
    onSettled: async (_data, _error, input) => {
      await removeQualityBody(client, input.id);
      await refresh(client);
    },
  });
}

export function withdrawCaseMutationOptions(client: QueryClient) {
  return mutationOptions({
    ...privateMutation,
    mutationKey: [...qualityKeys.all, "user", "withdrawCase"],
    mutationFn: (input: { id: string; body: Parameters<typeof api.withdrawCase>[1] }) =>
      api.withdrawCase(input.id, input.body),
    onMutate: (input) => removeQualityBody(client, input.id),
    onSettled: async (_data, _error, input) => {
      await removeQualityBody(client, input.id);
      await refresh(client);
    },
  });
}

export function closeCaseMutationOptions(client: QueryClient) {
  return mutationOptions({
    ...privateMutation,
    mutationKey: [...qualityKeys.all, "user", "closeCase"],
    mutationFn: (input: { id: string; body: Parameters<typeof api.closeCase>[1] }) =>
      api.closeCase(input.id, input.body),
    onMutate: (input) => removeQualityBody(client, input.id),
    onSettled: async (_data, _error, input) => {
      await removeQualityBody(client, input.id);
      await refresh(client);
    },
  });
}

export function assignCaseMutationOptions(client: QueryClient) {
  return mutationOptions({
    ...privateMutation,
    mutationKey: [...qualityKeys.all, "admin", "assignCase"],
    mutationFn: (input: { id: string; body: Parameters<typeof api.assignCase>[1] }) =>
      api.assignCase(input.id, input.body),
    onMutate: (input) => removeQualityBody(client, input.id),
    onSettled: async (_data, _error, input) => {
      await removeQualityBody(client, input.id);
      await refresh(client);
    },
  });
}

export function requestAccessMutationOptions(client: QueryClient) {
  return mutationOptions({
    ...privateMutation,
    mutationKey: [...qualityKeys.all, "admin", "requestAccess"],
    mutationFn: (input: { id: string; body: Parameters<typeof api.requestAccess>[1] }) =>
      api.requestAccess(input.id, input.body),
    onMutate: (input) => removeQualityBody(client, input.id),
    onSettled: async (_data, _error, input) => {
      await removeQualityBody(client, input.id);
      await refresh(client);
    },
  });
}

export function replayCaseMutationOptions(client: QueryClient) {
  return mutationOptions({
    ...privateMutation,
    mutationKey: [...qualityKeys.all, "admin", "replayCase"],
    mutationFn: (input: { id: string; body: Parameters<typeof api.replayCase>[1] }) =>
      api.replayCase(input.id, input.body),
    onMutate: (input) => removeQualityBody(client, input.id),
    onSettled: async (_data, _error, input) => {
      await removeQualityBody(client, input.id);
      await refresh(client);
    },
  });
}

export function addAdminMessageMutationOptions(client: QueryClient) {
  return mutationOptions({
    ...privateMutation,
    mutationKey: [...qualityKeys.all, "admin", "addAdminMessage"],
    mutationFn: (input: { id: string; body: Parameters<typeof api.addAdminMessage>[1] }) =>
      api.addAdminMessage(input.id, input.body),
    onMutate: (input) => removeQualityBody(client, input.id),
    onSettled: async (_data, _error, input) => {
      await removeQualityBody(client, input.id);
      await refresh(client);
    },
  });
}

export function transitionCaseMutationOptions(client: QueryClient) {
  return mutationOptions({
    ...privateMutation,
    mutationKey: [...qualityKeys.all, "admin", "transitionCase"],
    mutationFn: (input: { id: string; body: Parameters<typeof api.transitionCase>[1] }) =>
      api.transitionCase(input.id, input.body),
    onMutate: (input) => removeQualityBody(client, input.id),
    onSettled: async (_data, _error, input) => {
      await removeQualityBody(client, input.id);
      await refresh(client);
    },
  });
}
