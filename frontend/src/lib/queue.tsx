"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { ApiError, desk, type DeskSummary, type Label } from "./api";
import { signOut, useChecker } from "./session";

const POLL_MS = 5000; // new cases arrive while the checker works
const NOTICE_MS = 5000;

interface QueueState {
  items: DeskSummary[] | null;
  error: string | null;
  refresh: () => Promise<void>;
  // The last decision's confirmation. It lives here, not in the case view, because the desk
  // moves to the next case as soon as a decision is saved.
  notice: { text: string; shown: boolean };
  announce: (text: string) => void;
}

const QueueContext = createContext<QueueState | null>(null);

export function QueueProvider({ children }: { children: ReactNode }) {
  const { token } = useChecker();
  const [items, setItems] = useState<DeskSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState({ text: "", shown: false });

  const announce = useCallback((text: string) => setNotice({ text, shown: true }), []);

  // The text stays while hidden, so the confirmation fades out rather than vanishing.
  useEffect(() => {
    if (!notice.shown) return;
    const timer = setTimeout(() => setNotice((current) => ({ ...current, shown: false })), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);

  const refresh = useCallback(async () => {
    try {
      setItems(await desk.queue(token));
      setError(null);
    } catch (caught) {
      // A revoked code would otherwise keep polling and trip the API's wrong-code throttle.
      if (caught instanceof ApiError && caught.status === 401) signOut();
      else setError("Lost contact with the API. Retrying.");
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

  return <QueueContext.Provider value={{ items, error, refresh, notice, announce }}>{children}</QueueContext.Provider>;
}

export function useQueue(): QueueState {
  const queue = useContext(QueueContext);
  if (!queue) throw new Error("useQueue outside QueueProvider");
  return queue;
}

const LABELS: Label[] = ["false", "misleading", "true", "unverifiable"];

/** The desk's "?label=" filter, so a checker can clear one kind of draft at a time. */
export function useLabelFilter(): { label: Label | null; query: string } {
  const raw = useSearchParams().get("label");
  const label = LABELS.find((known) => known === raw) ?? null;
  return { label, query: label ? `?label=${label}` : "" };
}

export function matchesFilter(item: DeskSummary, label: Label | null): boolean {
  return label === null || item.proposed_label === label;
}
