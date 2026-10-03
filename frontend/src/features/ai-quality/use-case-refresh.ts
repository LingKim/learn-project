"use client";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
// 清正文会移除 active query；到期后换读取代次重新取无正文元数据，避免页面一直持有旧 Query 对象。
export function useCaseRefresh(role: "user" | "admin", id: string, version: number) {
  const client = useQueryClient();
  const [revision, setRevision] = useState(0);
  const busy = useRef(false);
  useEffect(
    () =>
      client.getQueryCache().subscribe((event) => {
        const key = event.query.queryKey;
        if (
          event.type === "removed" &&
          key[0] === "ai-quality" &&
          key[1] === role &&
          key[2] === "detail" &&
          key[3] === id &&
          key[4] === version &&
          key[5] === revision &&
          !busy.current
        )
          setRevision((value) => value + 1);
      }),
    [client, id, role, version, revision],
  );
  return { revision, busy, refresh: () => setRevision((value) => value + 1) };
}
