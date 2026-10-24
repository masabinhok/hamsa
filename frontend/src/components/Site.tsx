"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, site, type CaseStatus, type PublicCase } from "@/lib/api";
import { Both } from "@/components/Both";
import { Mark } from "@/components/Mark";
import { labelName } from "@/lib/words";
import styles from "../app/site.module.css";

// Limits enforced by the API (backend/app/api/main.py); checked here to fail early.
export const MAX_FILES = 4;
export const MAX_FILES_NE = "४";
export const ACCEPT = "image/jpeg,image/png,image/webp,video/mp4,video/webm";
const MINE_KEY = "hamsa.reports";
const MINE_MAX = 20;

// Reports sent from this browser, so a submitter can come back without keeping the link.
// Same store shape as the desk session (lib/session.tsx), in localStorage so it outlives the tab.
const mineListeners = new Set<() => void>();
let mineCache: string | undefined;

function mineSnapshot(): string {
  if (mineCache === undefined) {
    try {
      mineCache = localStorage.getItem(MINE_KEY) ?? "[]";
    } catch {
      mineCache = "[]";
    }
  }
  return mineCache;
}

function subscribeMine(listener: () => void): () => void {
  mineListeners.add(listener);
  return () => mineListeners.delete(listener);
}

function parseMine(raw: string): string[] {
  try {
    const stored: unknown = JSON.parse(raw);
    return Array.isArray(stored) ? stored.filter((id) => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function remember(id: string) {
  const ids = [id, ...parseMine(mineSnapshot()).filter((other) => other !== id)];
  mineCache = JSON.stringify(ids.slice(0, MINE_MAX));
  try {
    localStorage.setItem(MINE_KEY, mineCache);
  } catch {
    // Private windows can refuse storage; the report link still works.
  }
  mineListeners.forEach((listener) => listener());
}

export const steps: [string, string][] = [
  ["पठाइयो", "Sent"],
  ["Hamsa ले पोस्ट पढ्दै र प्रमाण खोज्दैछ", "Hamsa reads the post and looks for evidence"],
  ["तथ्य जाँचकर्ताले हेर्दै हुनुहुन्छ", "A fact-checker reviews it"],
  ["निर्णय प्रकाशित", "Verdict published"],
];

export const shortStatus: Record<CaseStatus, [string, string]> = {
  received: ["पठाइयो", "Sent"],
  processing: ["पढ्दैछ", "Reading"],
  routed: ["जाँच हुँदैछ", "Being checked"],
  merged: ["पहिले नै पठाइएको", "Already reported"],
  published: ["प्रकाशित", "Published"],
  rejected: ["दाबी छैन", "No claim"],
};

export function useMine(): string[] {
  const raw = useSyncExternalStore(subscribeMine, mineSnapshot, () => "[]");
  return parseMine(raw);
}

// Public pages share one top bar, so a reader can always get back to sending or browsing.
export function Masthead() {
  return (
    <header className={styles.masthead}>
      <Link href="/" className={styles.brand}>
        <Mark /> Hamsa <span className={styles.brandNe}>हंस</span>
      </Link>
      <nav className={styles.nav} aria-label="Hamsa">
        <Link href="/">पोस्ट पठाउनुहोस् · Send a post</Link>
        <Link href="/desk" lang="en" className={styles.deskLink}>
          Checker desk
        </Link>
      </nav>
    </header>
  );
}

export function Site() {
  const router = useRouter();

  function sent(id: string) {
    remember(id);
    router.push(`/check/${encodeURIComponent(id)}`);
  }

  return (
    <div className={styles.site} lang="ne">
      <Masthead />
      <section className={styles.sendPane} aria-labelledby="send-title">
        <SendForm onSent={sent} />
      </section>
      <section className={styles.statusPane} aria-label="Reports · रिपोर्टहरू">
        <section className={styles.group} aria-labelledby="after">
          <h2 id="after" className={styles.heading}>
            <Both ne="पठाएपछि के हुन्छ" en="What happens after you send" />
          </h2>
          <ol className={styles.journey}>
            {steps.map(([ne, en]) => (
              <li key={en}>
                <Both ne={ne} en={en} />
              </li>
            ))}
          </ol>
        </section>
        <Mine />
        <Recent />
      </section>
    </div>
  );
}

function SendForm({ onSent }: { onSent: (id: string) => void }) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<[string, string] | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

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
      setError([`बढीमा ${MAX_FILES_NE} वटा फाइल जोड्नुहोस्।`, `Attach at most ${MAX_FILES} files.`]);
      return;
    }
    if (!hasLink) form.delete("url");
    setSending(true);
    setError(null);
    try {
      const { id } = await site.submit(form);
      formRef.current?.reset();
      onSent(id);
    } catch (failure) {
      setError(
        failure instanceof ApiError && failure.status === 429
          ? ["यहाँबाट धेरै पठाइयो। एक मिनेट पर्खनुहोस्।", "Too many submissions from here. Please wait a minute."]
          : failure instanceof ApiError && failure.status === 422
            ? [
                "यो लिंक जाँच्न मिल्दैन। Facebook, TikTok, X, YouTube वा Instagram को पोस्टको लिंक पठाउनुहोस्।",
                `This link cannot be checked: ${failure.message}.`,
              ]
            : [
              "पठाउन सकिएन। फेरि प्रयास गर्नुहोस्।",
              `Could not send it: ${failure instanceof Error ? failure.message : "unknown error"}.`,
            ],
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <header className={styles.header}>
        <h1 id="send-title" className={styles.title}>
          विपद्‌बारे शंकास्पद पोस्ट देख्नुभयो?
        </h1>
        <p className={styles.lede}>
          <Both
            ne="बाढी, पहिरो, भूकम्प वा अरू विपद्‌को पोस्ट यहाँ पठाउनुहोस्। तथ्य जाँचकर्ताहरूले हरेक पोस्ट हेर्छन् र आफूले भेटेको कुरा प्रकाशित गर्छन्।"
            en="Seen a doubtful post about a flood, landslide, earthquake or other disaster in Nepal? Send it here. Fact-checkers look at every post and publish what they find."
          />
        </p>
      </header>

      <form ref={formRef} className={styles.form} onSubmit={submit}>
        <label className={styles.field}>
          <Both ne="पोस्टको लिंक" en="Link to the post (Facebook, TikTok, YouTube, X, Instagram)" />
          <input name="url" type="url" inputMode="url" placeholder="https://" lang="en" />
        </label>
        <label className={styles.field}>
          <Both ne="पोस्टमा लेखिएको कुरा" en="What the post says" />
          <textarea name="text" rows={3} maxLength={5000} />
        </label>
        <p className={styles.hint}>
          <Both
            ne="लिंक मात्र भए पनि हुन्छ। हामी पोस्ट खोल्न सकेनौं भने फोटो वा भिडियो माग्नेछौं।"
            en="A link alone is enough. If we cannot open the post, we will ask you for the photo or video."
          />
        </p>
        {/* Uploading is the slow part, so it waits behind the link (Oct 23 feedback). */}
        <details className={styles.more}>
          <summary>
            <Both ne="फोटो वा भिडियो पहिले नै छ?" en="Already have the photo or video?" />
          </summary>
          <label className={styles.field}>
            <Both
              ne={`फोटो वा भिडियो (बढीमा ${MAX_FILES_NE} वटा, प्रत्येक १०० MB सम्म)`}
              en={`Its photos or video (up to ${MAX_FILES}, 100 MB each)`}
            />
            <input name="files" type="file" accept={ACCEPT} multiple />
          </label>
        </details>
        {error && (
          <p className={styles.error} role="alert">
            <Both ne={error[0]} en={error[1]} />
          </p>
        )}
        <div className={styles.submitBar}>
          <button className={styles.submit} disabled={sending}>
            {sending ? "पठाउँदै… Sending…" : "जाँचका लागि पठाउनुहोस् · Send for checking"}
          </button>
        </div>
      </form>
    </>
  );
}

function date(iso: string): string {
  return new Date(iso).toLocaleDateString("ne-NP", { day: "numeric", month: "short" });
}

// `compact` is the side list beside an open report; the home page shows cards.
export function Mine({ selected = null, compact = false }: { selected?: string | null; compact?: boolean }) {
  const ids = useMine();
  const key = ids.join();
  const [found, setFound] = useState<Record<string, PublicCase>>({});

  // Keyed on the joined ids: the array itself is new on every render. Re-read on navigation
  // so the statuses beside an open report stay current.
  useEffect(() => {
    key
      .split(",")
      .filter(Boolean)
      .forEach((id) =>
        site.case(id).then(
          (item) => setFound((all) => ({ ...all, [id]: item })),
          () => undefined,
        ),
      );
  }, [key, selected]);

  if (ids.length === 0) return null;
  return (
    <section className={styles.group} aria-labelledby="mine">
      <h2 id="mine" className={styles.heading}>
        <Both ne="तपाईंले पठाएका" en="Sent from this browser" />
      </h2>
      <ul className={styles.list} data-compact={compact ? "" : undefined}>
        {ids.map((id) => {
          const item = found[id];
          const label = item?.verdict?.label;
          return (
            <li key={id}>
              <Link
                href={`/check/${encodeURIComponent(id)}`}
                className={styles.item}
                aria-current={id === selected ? "page" : undefined}
              >
                {label ? (
                  <span className={styles.pill} data-label={label}>
                    {labelName[label].ne} <span lang="en">{labelName[label].en}</span>
                  </span>
                ) : item ? (
                  <span className={styles.chip}>
                    {shortStatus[item.status][0]} <span lang="en">{shortStatus[item.status][1]}</span>
                  </span>
                ) : null}
                <span className={styles.itemText}>{item?.text ?? item?.source_url ?? id}</span>
                <span className={styles.quiet} lang="en">
                  {id}
                  {item && ` · ${date(item.created_at)}`}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function Recent({
  selected = null,
  compact = false,
}: {
  selected?: string | null;
  compact?: boolean;
}) {
  const [recent, setRecent] = useState<PublicCase[] | null>(null);

  useEffect(() => {
    site.verdicts().then(setRecent, () => setRecent([]));
  }, []);

  const shown = (recent ?? []).filter((item) => item.verdict).slice(0, compact ? 30 : 12);
  return (
    <section className={styles.group} aria-labelledby="recent">
      <h2 id="recent" className={styles.heading}>
        <Both ne="भर्खरै जाँचिएका" en="Recently checked" />
      </h2>
      {recent !== null && shown.length === 0 && (
        <p className={styles.empty}>
          <Both
            ne="अहिलेसम्म कुनै निर्णय प्रकाशित भएको छैन। जाँचिएका पोस्टहरू यहाँ देखिनेछन्।"
            en="No verdicts published yet. Checked posts will appear here."
          />
        </p>
      )}
      <ul
        className={styles.list}
        data-cards={compact ? undefined : ""}
        data-compact={compact ? "" : undefined}
      >
        {shown.map((item) =>
          item.verdict ? (
            <li key={item.id}>
              <Link
                href={`/check/${encodeURIComponent(item.id)}`}
                className={styles.item}
                aria-current={item.id === selected ? "page" : undefined}
              >
                <span className={styles.pill} data-label={item.verdict.label}>
                  {labelName[item.verdict.label].ne} <span lang="en">{labelName[item.verdict.label].en}</span>
                </span>
                <span className={styles.itemTitle}>
                  {item.verdict.claim?.claim ?? item.text ?? item.verdict.rationale_ne}
                </span>
                {!compact && <span className={styles.itemText}>{item.verdict.rationale_ne}</span>}
                <span className={styles.quiet}>{date(item.verdict.published_at)}</span>
              </Link>
            </li>
          ) : null,
        )}
      </ul>
    </section>
  );
}
