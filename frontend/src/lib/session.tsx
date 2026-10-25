"use client";

import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";

// The checker's token and name live in sessionStorage, so closing the tab signs out, unless
// they chose to stay signed in on this device: then localStorage keeps them.
export interface Checker {
  token: string;
  name: string;
}

const KEY = "hamsa.checker";
const listeners = new Set<() => void>();

function read(): string | null {
  try {
    return sessionStorage.getItem(KEY) ?? localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function signIn(checker: Checker, remember = false): void {
  try {
    (remember ? localStorage : sessionStorage).setItem(KEY, JSON.stringify(checker));
  } catch {
    // Storage blocked: the session lasts until the next reload.
  }
  cache = JSON.stringify(checker);
  listeners.forEach((listener) => listener());
}

export function signOut(): void {
  try {
    sessionStorage.removeItem(KEY);
    localStorage.removeItem(KEY);
  } catch {}
  cache = null;
  listeners.forEach((listener) => listener());
}

let cache: string | null | undefined;

function snapshot(): string | null {
  if (cache === undefined) cache = read();
  return cache;
}

const CheckerContext = createContext<Checker | null>(null);

export function useStoredChecker(): Checker | null {
  const raw = useSyncExternalStore(subscribe, snapshot, () => null);
  return raw ? (JSON.parse(raw) as Checker) : null;
}

export function CheckerProvider({ checker, children }: { checker: Checker; children: ReactNode }) {
  return <CheckerContext.Provider value={checker}>{children}</CheckerContext.Provider>;
}

export function useChecker(): Checker {
  const checker = useContext(CheckerContext);
  if (!checker) throw new Error("useChecker outside the signed-in desk");
  return checker;
}
