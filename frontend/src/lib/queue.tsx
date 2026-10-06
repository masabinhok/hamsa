"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { desk, type DeskSummary } from "./api";
import { useChecker } from "./session";

const POLL_MS = 5000; // new cases arrive while the checker works

interface QueueState {
  items: DeskSummary[] | null;
  error: string | null;
  refresh: () => Promise<void>;
}

const QueueContext = createContext<QueueState | null>(null);

export function QueueProvider({ children }: { children: ReactNode }) {
  const { token } = useChecker();
  const [items, setItems] = useState<DeskSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setItems(await desk.queue(token));
      setError(null);
    } catch {
      setError("Lost contact with the API. Retrying.");
    }
  }, [token]);

  useEffect(() => {
    const first = setTimeout(refresh, 0);
    const timer = setInterval(refresh, POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [refresh]);

  return <QueueContext.Provider value={{ items, error, refresh }}>{children}</QueueContext.Provider>;
}

export function useQueue(): QueueState {
  const queue = useContext(QueueContext);
  if (!queue) throw new Error("useQueue outside QueueProvider");
  return queue;
}
