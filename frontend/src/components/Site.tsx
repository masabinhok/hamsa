"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore, ViewTransition } from "react";
import { ApiError, site, type CaseStatus, type Label, type PublicCase } from "@/lib/api";
import { Both } from "@/components/Both";
import { Mark } from "@/components/Mark";
import { labelName, timeAgoNe } from "@/lib/words";
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
      <div className={styles.mastheadInner}>
        <Link href="/" className={styles.brand}>
          <Mark /> Hamsa <span className={styles.brandNe}>हंस</span>
        </Link>
        <nav className={styles.nav} aria-label="Hamsa">
          <Link href="/#checked">जाँचिएका</Link>
          <Link href="/#send">पोस्ट पठाउनुहोस्</Link>
          <Link href="/desk" lang="en" className={styles.deskLink}>
            Checker desk
          </Link>
        </nav>
      </div>
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
      {/* Page changes crossfade; the bar above stays put. */}
      <ViewTransition>
        <main className={styles.page}>
        <section id="send" className={styles.send} aria-labelledby="send-title">
          <SendForm onSent={sent} />
        </section>
        <div className={styles.columns}>
          <Recent />
          <aside className={styles.rail} aria-label="तपाईंका रिपोर्ट र जाँच कसरी हुन्छ · Your reports and how a check works">
            <Mine />
            <section className={styles.panel} aria-labelledby="after">
              <h2 id="after" className={styles.heading}>
                <Both ne="पठाएपछि के हुन्छ" en="What happens after you send" />
              </h2>
              <ol className={styles.journey}>
                {steps.map(([ne, en]) => (
                  <li key={en}>
                    <span>
                      <Both ne={ne} en={en} />
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          </aside>
        </div>
        </main>
      </ViewTransition>
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
      <header>
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

const IMAGE = /\.(jpe?g|png|webp)$/i;

// The post's first published picture or video frame; the swan on the verdict's colour if none.
export function Thumb({ item, eager = false }: { item: PublicCase; eager?: boolean }) {
  const media = item.verdict?.media ?? [];
  const image = media.find((name) => IMAGE.test(name));
  const video = media.find((name) => !IMAGE.test(name));
  return (
    <span className={styles.thumb} data-label={item.verdict?.label}>
      {image ? (
        // eslint-disable-next-line @next/next/no-img-element -- the API serves it; nothing to optimise
        <img src={site.mediaUrl(item.id, image)} alt="" loading={eager ? "eager" : "lazy"} />
      ) : video ? (
        <>
          {/* #t= asks for a frame a second in, so the card shows the scene, not a black start. */}
          <video src={`${site.mediaUrl(item.id, video)}#t=1`} preload="metadata" muted playsInline aria-hidden="true" tabIndex={-1} />
          <span className={styles.play} aria-hidden="true">
            ▶ भिडियो
          </span>
        </>
      ) : (
        <span className={styles.thumbEmpty}>
          <Mark size={64} />
        </span>
      )}
    </span>
  );
}

export function Tag({ label }: { label: Label }) {
  return (
    <span className={styles.tag} data-label={label}>
      {labelName[label].ne} <span lang="en">{labelName[label].en}</span>
    </span>
  );
}

function headline(item: PublicCase): string {
  return item.verdict?.claim?.claim ?? item.text ?? item.verdict?.rationale_ne ?? item.id;
}

// The reader's own reports, newest first, in the side rail.
export function Mine({ selected = null }: { selected?: string | null }) {
  const ids = useMine();
  const key = ids.join();
  const [found, setFound] = useState<Record<string, PublicCase>>({});

  // Keyed on the joined ids: the array itself is new on every render. Re-read on navigation
  // so the statuses stay current.
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
    <section className={styles.panel} aria-labelledby="mine">
      <h2 id="mine" className={styles.heading}>
        <Both ne="तपाईंले पठाएका" en="Sent from this browser" />
      </h2>
      <ul className={styles.list}>
        {ids.map((id) => {
          const item = found[id];
          const label = item?.verdict?.label;
          return (
            <li key={id}>
              <Link
                href={`/check/${encodeURIComponent(id)}`}
                className={styles.row}
                aria-current={id === selected ? "page" : undefined}
              >
                {label ? (
                  <Tag label={label} />
                ) : item ? (
                  <span className={styles.chip}>
                    {shortStatus[item.status][0]} <span lang="en">{shortStatus[item.status][1]}</span>
                  </span>
                ) : null}
                <span className={styles.rowTitle}>{item ? headline(item) : id}</span>
                <span className={styles.quiet}>{item ? timeAgoNe(item.created_at) : ""}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// The front page of checked posts: the newest leads, the rest as news cards. `compact` is the
// "more checked posts" list under an article.
export function Recent({ selected = null, compact = false }: { selected?: string | null; compact?: boolean }) {
  const [recent, setRecent] = useState<PublicCase[] | null>(null);

  useEffect(() => {
    site.verdicts().then(setRecent, () => setRecent([]));
  }, []);

  const shown = (recent ?? []).filter((item) => item.verdict && item.id !== selected).slice(0, compact ? 6 : 13);
  const [lead, ...rest] = compact ? [undefined, ...shown] : shown;
  return (
    <section id="checked" className={styles.feed} aria-labelledby="recent">
      <h2 id="recent" className={styles.heading}>
        {compact ? (
          <Both ne="अरू जाँचिएका पोस्ट" en="More checked posts" />
        ) : (
          <Both ne="भर्खरै जाँचिएका" en="Recently checked" />
        )}
      </h2>
      {recent === null && (
        <div aria-label="लोड हुँदैछ · Loading" role="status">
          {[0, 1, 2].map((n) => (
            <div key={n} className={styles.skeleton} aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          ))}
        </div>
      )}
      {recent !== null && shown.length === 0 && (
        <p className={styles.empty}>
          <Both
            ne="अहिलेसम्म कुनै निर्णय प्रकाशित भएको छैन। जाँचिएका पोस्टहरू यहाँ देखिनेछन्।"
            en="No verdicts published yet. Checked posts will appear here."
          />
        </p>
      )}
      {lead?.verdict && (
        <Link href={`/check/${encodeURIComponent(lead.id)}`} className={styles.lead} data-label={lead.verdict.label}>
          <Thumb item={lead} eager />
          <Tag label={lead.verdict.label} />
          <span className={styles.cardTitle}>{headline(lead)}</span>
          <span className={styles.cardExcerpt}>{lead.verdict.rationale_ne}</span>
          <span className={styles.quiet}>{timeAgoNe(lead.verdict.published_at)}</span>
        </Link>
      )}
      <ul className={styles.list}>
        {rest.map((item) =>
          item?.verdict ? (
            <li key={item.id}>
              <Link href={`/check/${encodeURIComponent(item.id)}`} className={styles.card} data-label={item.verdict.label}>
                <span className={styles.cardText}>
                  <Tag label={item.verdict.label} />
                  <span className={styles.cardTitle}>{headline(item)}</span>
                  {!compact && <span className={styles.cardExcerpt}>{item.verdict.rationale_ne}</span>}
                  <span className={styles.quiet}>{timeAgoNe(item.verdict.published_at)}</span>
                </span>
                <Thumb item={item} />
              </Link>
            </li>
          ) : null,
        )}
      </ul>
    </section>
  );
}
