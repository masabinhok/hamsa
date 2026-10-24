"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { ApiError, desk, site } from "@/lib/api";
import { Mark } from "@/components/Mark";
import { signIn } from "@/lib/session";
import styles from "./SignIn.module.css";

const VERDICTS_LISTED = 50; // the API lists at most this many recent verdicts

export function SignIn() {
  const [code, setCode] = useState("");
  const [shown, setShown] = useState(false);
  const [remember, setRemember] = useState(false);
  // Only the operator token needs a typed name; a checker's own code already names them.
  const [askName, setAskName] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [published, setPublished] = useState<number | null>(null);

  useEffect(() => {
    site.verdicts().then((all) => setPublished(all.length), () => undefined);
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setChecking(true);
    setError(null);
    try {
      const { name: owner } = await desk.me(code);
      if (owner) {
        signIn({ name: owner, token: code }, remember);
      } else if (name.trim()) {
        signIn({ name: name.trim(), token: code }, remember);
      } else {
        setAskName(true);
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        setError("That access code is not recognised. Ask whoever runs your desk for a new one.");
      } else if (caught instanceof ApiError && caught.status === 429) {
        setError("Too many wrong codes from this network. Wait a minute, then try again.");
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
      <section className={styles.intro} aria-labelledby="desk-title">
        <p className={styles.brand}>
          <Mark size={40} /> Hamsa <span lang="ne">हंस</span>
        </p>
        <h1 id="desk-title" className={styles.title}>
          The checker desk
        </h1>
        <p className={styles.lede}>
          Posts about floods, landslides and earthquakes in Nepal arrive here already read: Hamsa
          extracts the claim, looks for earlier copies of the footage, gathers news and fact-checks,
          and drafts a verdict. A checker decides what is published.
        </p>
        <ol className={styles.points}>
          <li>
            <strong>Sorted by evidence.</strong> Quick checks first, then cases that need a closer look.
          </li>
          <li>
            <strong>Every source shown.</strong> The draft cites what it relied on, side by side with the post.
          </li>
          <li>
            <strong>You decide.</strong> Publish, edit, relabel or reject. Every decision is recorded under your name.
          </li>
        </ol>
        {published ? (
          <p className={styles.stat}>
            <span className={styles.statNumber}>
              {published}
              {published >= VERDICTS_LISTED && "+"}
            </span>{" "}
            verdicts published so far
          </p>
        ) : null}
        <Link href="/" className={styles.back}>
          Back to the public site
        </Link>
      </section>

      <section className={styles.formSide}>
        <form className={styles.form} onSubmit={submit}>
          <h2 className={styles.formTitle}>Sign in</h2>
          <p className={styles.hint}>Use the access code you were given. It names you, so keep it to yourself.</p>
          <label className={styles.field}>
            Access code
            <span className={styles.codeRow}>
              <input
                type={shown ? "text" : "password"}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
                autoComplete="current-password"
                spellCheck={false}
                autoFocus
              />
              <button
                type="button"
                className={styles.reveal}
                aria-pressed={shown}
                onClick={() => setShown(!shown)}
              >
                {shown ? "Hide" : "Show"}
              </button>
            </span>
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
          <label className={styles.check}>
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            Keep me signed in on this device
          </label>
          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
          <button className={styles.submit} disabled={checking || !code || (askName && !name.trim())}>
            {checking ? "Checking…" : "Open the desk"}
          </button>
          <p className={styles.hint}>
            Only on a shared computer: leave &ldquo;keep me signed in&rdquo; off, and the desk forgets you when
            the tab closes.
          </p>
        </form>
      </section>
    </main>
  );
}
