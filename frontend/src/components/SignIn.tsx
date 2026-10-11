"use client";

import { useState, type FormEvent } from "react";
import { ApiError, desk } from "@/lib/api";
import { signIn } from "@/lib/session";
import styles from "./SignIn.module.css";

export function SignIn() {
  const [name, setName] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setChecking(true);
    setError(null);
    try {
      await desk.queue(token);
      signIn({ name: name.trim(), token });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        setError("That desk token is not right. Check DESK_TOKEN in the server's .env.");
      } else if (caught instanceof ApiError && caught.status === 503) {
        setError("The desk is switched off. Set DESK_TOKEN on the server and restart it.");
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
          Sign in to the checker desk. Your name goes on every verdict you publish.
        </p>
        <label className={styles.field}>
          Your name
          <input value={name} onChange={(e) => setName(e.target.value)} required autoComplete="name" />
        </label>
        <label className={styles.field}>
          Desk token
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            required
            autoComplete="current-password"
          />
        </label>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <button className={styles.submit} disabled={checking || !name.trim() || !token}>
          {checking ? "Checking…" : "Open the desk"}
        </button>
      </form>
    </main>
  );
}
