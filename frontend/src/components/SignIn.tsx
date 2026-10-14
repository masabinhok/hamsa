"use client";

import { useState, type FormEvent } from "react";
import { ApiError, desk } from "@/lib/api";
import { signIn } from "@/lib/session";
import styles from "./SignIn.module.css";

export function SignIn() {
  const [code, setCode] = useState("");
  // Only the operator token needs a typed name; a checker's own code already names them.
  const [askName, setAskName] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setChecking(true);
    setError(null);
    try {
      const { name: owner } = await desk.me(code);
      if (owner) {
        signIn({ name: owner, token: code });
      } else if (name.trim()) {
        signIn({ name: name.trim(), token: code });
      } else {
        setAskName(true);
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        setError("That access code is not recognised. Ask whoever runs your desk for a new one.");
      } else if (caught instanceof ApiError && caught.status === 503) {
        setError("The desk has no checkers yet. On the server run: python -m app.checkers add \"Your Name\"");
      } else {
        setError("Cannot reach the Hamsa API. Is it running on port 8000?");
      }
    } finally {
      setChecking(false);
    }
  }

  return (
    <main className={styles.page}>
      <form className={styles.form} onSubmit={submit}>
        <h1 className={styles.title}>Hamsa</h1>
        <p className={styles.lede}>
          Sign in to the checker desk with your access code. Your name goes on every verdict you
          publish.
        </p>
        <label className={styles.field}>
          Access code
          <input
            type="password"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
            autoComplete="current-password"
          />
        </label>
        {askName && (
          <label className={styles.field}>
            Operator key: who is deciding?
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoComplete="name"
              autoFocus
            />
          </label>
        )}
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <button className={styles.submit} disabled={checking || !code || (askName && !name.trim())}>
          {checking ? "Checking…" : "Open the desk"}
        </button>
      </form>
    </main>
  );
}
