"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, site, type PublicCase } from "@/lib/api";
import { Both } from "@/components/Both";
import { labelName } from "@/lib/words";
import styles from "./site.module.css";

// Limits enforced by the API (backend/app/api/main.py); checked here to fail early.
const MAX_FILES = 4;
const MAX_FILES_NE = "४";
const ACCEPT = "image/jpeg,image/png,image/webp,video/mp4,video/webm";

export default function Home() {
  const router = useRouter();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<[string, string] | null>(null);
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
      setError([
        "पोस्टको लिंक वा लेखिएको कुरा राख्नुहोस्, वा फोटो/भिडियो जोड्नुहोस्।",
        "Paste the post's link or text, or attach its photo or video.",
      ]);
      return;
    }
    if (files.length > MAX_FILES) {
      setError([
        `बढीमा ${MAX_FILES_NE} वटा फाइल जोड्नुहोस्।`,
        `Attach at most ${MAX_FILES} files.`,
      ]);
      return;
    }
    if (!String(form.get("url") ?? "").trim()) form.delete("url");
    setSending(true);
    setError(null);
    try {
      const { id } = await site.submit(form);
      router.push(`/check/${id}`);
    } catch (failure) {
      setError(
        failure instanceof ApiError && failure.status === 429
          ? ["यहाँबाट धेरै पठाइयो। एक मिनेट पर्खनुहोस्।", "Too many submissions from here. Please wait a minute."]
          : [
              "पठाउन सकिएन। फेरि प्रयास गर्नुहोस्।",
              `Could not send it: ${failure instanceof Error ? failure.message : "unknown error"}.`,
            ],
      );
      setSending(false);
    }
  }

  return (
    <main className={styles.page} lang="ne">
      <header className={styles.header}>
        <p className={styles.brand}>Hamsa</p>
        <h1 className={styles.title}>बाढी, पहिरो, भूकम्प वा अरू विपद्‌बारे शंकास्पद पोस्ट देख्नुभयो?</h1>
        <p className={styles.lede}>
          <Both
            ne="यहाँ पठाउनुहोस्। तथ्य जाँचकर्ताहरूले हरेक पोस्ट हेर्छन् र आफूले भेटेको कुरा प्रकाशित गर्छन्।"
            en="Seen a doubtful post about a disaster in Nepal? Send it here. Fact-checkers look at every post and publish what they find."
          />
        </p>
      </header>

      <form className={styles.form} onSubmit={submit}>
        <label className={styles.field}>
          <Both ne="पोस्टको लिंक" en="Link to the post (Facebook, TikTok, YouTube, X)" />
          <input name="url" type="url" inputMode="url" placeholder="https://" lang="en" />
        </label>
        <label className={styles.field}>
          <Both ne="पोस्टमा लेखिएको कुरा" en="The post's text" />
          <textarea name="text" rows={5} maxLength={5000} />
        </label>
        <label className={styles.field}>
          <Both
            ne={`फोटो वा भिडियो (बढीमा ${MAX_FILES_NE} वटा, प्रत्येक १०० MB सम्म)`}
            en={`Its photos or video (up to ${MAX_FILES}, 100 MB each)`}
          />
          <input name="files" type="file" accept={ACCEPT} multiple />
        </label>
        {error && (
          <p className={styles.error} role="alert">
            <Both ne={error[0]} en={error[1]} />
          </p>
        )}
        <button className={styles.submit} disabled={sending}>
          {sending ? "पठाउँदै… Sending…" : "जाँचका लागि पठाउनुहोस् · Send for checking"}
        </button>
      </form>

      {recent.length > 0 && (
        <section className={styles.recent} aria-labelledby="recent">
          <h2 id="recent" className={styles.heading}>
            <Both ne="भर्खरै जाँचिएका" en="Recently checked" />
          </h2>
          <ul className={styles.list}>
            {recent.slice(0, 10).map((item) =>
              item.verdict ? (
                <li key={item.id}>
                  <Link href={`/check/${item.id}`} className={styles.item}>
                    <span className={styles.label} data-label={item.verdict.label}>
                      {labelName[item.verdict.label].ne}{" "}
                      <span lang="en">· {labelName[item.verdict.label].en}</span>
                    </span>
                    <span>{item.verdict.rationale_ne}</span>
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
