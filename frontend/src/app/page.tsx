"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, site, type PublicCase } from "@/lib/api";
import { labelName } from "@/lib/words";
import styles from "./site.module.css";

// Limits enforced by the API (backend/app/api/main.py); checked here to fail early.
const MAX_FILES = 4;
const ACCEPT = "image/jpeg,image/png,image/webp,video/mp4,video/webm";

export default function Home() {
  const router = useRouter();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [recent, setRecent] = useState<PublicCase[]>([]);

  useEffect(() => {
    site.verdicts().then(setRecent, () => setRecent([]));
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const files = form.getAll("files").filter((f) => f instanceof File && f.size > 0);
    form.delete("files");
    files.forEach((file) => form.append("files", file));
    const hasLink = String(form.get("url") ?? "").trim() !== "";
    if (!String(form.get("text") ?? "").trim() && files.length === 0 && !hasLink) {
      setError("Paste the post's link or text, or attach its photo or video.");
      return;
    }
    if (files.length > MAX_FILES) {
      setError(`Attach at most ${MAX_FILES} files.`);
      return;
    }
    if (!String(form.get("url") ?? "").trim()) form.delete("url");
    setSending(true);
    setError("");
    try {
      const { id } = await site.submit(form);
      router.push(`/check/${id}`);
    } catch (failure) {
      setError(
        failure instanceof ApiError && failure.status === 429
          ? "Too many submissions from here. Please wait a minute."
          : `Could not send it: ${failure instanceof Error ? failure.message : "unknown error"}.`,
      );
      setSending(false);
    }
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <p className={styles.brand}>Hamsa</p>
        <h1 className={styles.title} lang="ne">
          बाढी, पहिरो वा भूकम्पबारे शंकास्पद पोस्ट देख्नुभयो?
        </h1>
        <p className={styles.lede}>
          Seen a doubtful post about a flood, landslide or earthquake in Nepal? Send it here.
          Fact-checkers look at every post and publish what they find.
        </p>
      </header>

      <form className={styles.form} onSubmit={submit}>
        <label className={styles.field}>
          <span>The post&rsquo;s text</span>
          <textarea name="text" rows={5} maxLength={5000} lang="ne" />
        </label>
        <label className={styles.field}>
          <span>Link to the post</span>
          <input name="url" type="url" inputMode="url" placeholder="https://" />
        </label>
        <label className={styles.field}>
          <span>Its photos or video (up to {MAX_FILES}, 100 MB each)</span>
          <input name="files" type="file" accept={ACCEPT} multiple />
        </label>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <button className={styles.submit} disabled={sending}>
          {sending ? "Sending…" : "Send for checking"}
        </button>
      </form>

      {recent.length > 0 && (
        <section className={styles.recent} aria-labelledby="recent">
          <h2 id="recent" className={styles.heading}>
            Recently checked
          </h2>
          <ul className={styles.list}>
            {recent.slice(0, 10).map((item) =>
              item.verdict ? (
                <li key={item.id}>
                  <Link href={`/check/${item.id}`} className={styles.item}>
                    <span className={styles.label} data-label={item.verdict.label}>
                      {labelName[item.verdict.label].en}
                    </span>
                    <span lang="ne">{item.verdict.rationale_ne}</span>
                  </Link>
                </li>
              ) : null,
            )}
          </ul>
        </section>
      )}
    </main>
  );
}
