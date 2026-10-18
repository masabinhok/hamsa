"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, site, type CaseStatus, type PublicCase } from "@/lib/api";
import { Both } from "@/components/Both";
import { labelName } from "@/lib/words";
import styles from "../app/site.module.css";

// Limits enforced by the API (backend/app/api/main.py); checked here to fail early.
const MAX_FILES = 4;
const MAX_FILES_NE = "४";
const ACCEPT = "image/jpeg,image/png,image/webp,video/mp4,video/webm";
const POLL_MS = 5000;
const FINAL: CaseStatus[] = ["published", "rejected", "merged"];
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

const steps: [string, string][] = [
  ["पठाइयो", "Sent"],
  ["Hamsa ले पोस्ट पढ्दै र प्रमाण खोज्दैछ", "Hamsa reads the post and looks for evidence"],
  ["तथ्य जाँचकर्ताले हेर्दै हुनुहुन्छ", "A fact-checker reviews it"],
  ["निर्णय प्रकाशित", "Verdict published"],
];

// Which step a status has reached; merged and rejected replace the step they end on.
const reached: Record<CaseStatus, number> = {
  received: 0,
  processing: 1,
  routed: 2,
  merged: 2,
  published: 3,
  rejected: 3,
};

const endings: Partial<Record<CaseStatus, [string, string]>> = {
  merged: [
    "यो पोस्ट पहिले नै कसैले पठाइसक्नुभएको छ। त्यही रिपोर्टमा जाँच भइरहेको छ।",
    "Someone already sent this post. It is being checked under that report.",
  ],
  rejected: [
    "निर्णय प्रकाशित भएन: पोस्टमा जाँच्न मिल्ने तथ्यगत दाबी छैन।",
    "No verdict was published: the post makes no factual claim that can be checked.",
  ],
};

const shortStatus: Record<CaseStatus, [string, string]> = {
  received: ["पठाइयो", "Sent"],
  processing: ["पढ्दैछ", "Reading"],
  routed: ["जाँच हुँदैछ", "Being checked"],
  merged: ["पहिले नै पठाइएको", "Already reported"],
  published: ["प्रकाशित", "Published"],
  rejected: ["दाबी छैन", "No claim"],
};

export function Site() {
  // The URL is the selection, so back and forward move between reports.
  const match = /^\/check\/([^/]+)/.exec(usePathname());
  const selected = match ? decodeURIComponent(match[1]) : null;
  const mineRaw = useSyncExternalStore(subscribeMine, mineSnapshot, () => "[]");

  // Swap the report on the right without reloading, so a half-filled form on the left survives.
  function open(id: string) {
    window.history.pushState(null, "", `/check/${encodeURIComponent(id)}`);
  }

  function sent(id: string) {
    remember(id);
    open(id);
  }

  return (
    <div className={styles.site} lang="ne" data-open={selected ? "" : undefined}>
      <section className={styles.sendPane} aria-labelledby="send-title">
        <SendForm onSent={sent} />
      </section>
      <section className={styles.statusPane} aria-label="Status · स्थिति">
        {selected ? (
          <Status key={selected} id={selected} />
        ) : (
          <p className={styles.empty}>
            <Both
              ne="पोस्ट पठाएपछि यसको जाँच कहाँ पुग्यो, यहाँ देखिन्छ।"
              en="Once you send a post, you can follow its check here."
            />
          </p>
        )}
        <Mine raw={mineRaw} selected={selected} onOpen={open} />
        <Recent selected={selected} onOpen={open} />
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
        <Link href="/" className={styles.brand}>
          Hamsa <span className={styles.brandNe}>हंस</span>
        </Link>
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
          <Both ne="पोस्टको लिंक" en="Link to the post (Facebook, TikTok, YouTube, X)" />
          <input name="url" type="url" inputMode="url" placeholder="https://" lang="en" />
        </label>
        <label className={styles.field}>
          <Both ne="पोस्टमा लेखिएको कुरा" en="What the post says" />
          <textarea name="text" rows={3} maxLength={5000} />
        </label>
        <label className={styles.field}>
          <Both
            ne={`फोटो वा भिडियो (बढीमा ${MAX_FILES_NE} वटा, प्रत्येक १०० MB सम्म)`}
            en={`Its photos or video (up to ${MAX_FILES}, 100 MB each)`}
          />
          <input name="files" type="file" accept={ACCEPT} multiple />
        </label>
        <p className={styles.hint}>
          <Both
            ne="लिंक मात्र भए पनि हुन्छ। पोस्ट निजी छ भने फोटो वा भिडियो जोड्नुहोस्।"
            en="A link alone is enough. If the post is private, attach the photo or video."
          />
        </p>
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

function usePublicCase(id: string) {
  const [current, setCurrent] = useState<PublicCase | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const load = () =>
      site.case(id).then(
        (found) => {
          if (stopped) return;
          setCurrent(found);
          if (!FINAL.includes(found.status)) timer = setTimeout(load, POLL_MS);
        },
        (failure) => {
          if (stopped) return;
          if (failure instanceof ApiError && failure.status === 404) setMissing(true);
          else timer = setTimeout(load, POLL_MS);
        },
      );
    load();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [id]);

  return { current, missing };
}

function Status({ id }: { id: string }) {
  const { current, missing } = usePublicCase(id);
  const verdict = current?.verdict;
  const step = current ? reached[current.status] : -1;
  const ending = current ? endings[current.status] : undefined;

  return (
    <article className={styles.status} aria-live="polite">
      <p className={styles.quiet}>
        <Both
          ne={`रिपोर्ट नं. ${id}। यो पेजको लिंक राखे पछि फेरि हेर्न सकिन्छ।`}
          en={`Report ${id}. Keep this page's link to come back to it.`}
        />
      </p>

      {missing && (
        <p className={styles.error} role="alert">
          <Both ne="यो नम्बरको कुनै रिपोर्ट छैन।" en="There is no report with this number." />
        </p>
      )}
      {!missing && !current && <p className={styles.quiet}>लोड हुँदैछ… Loading…</p>}

      {current && !verdict && (
        <ol className={styles.steps}>
          {steps.map(([ne, en], index) => {
            const last = index === step && ending;
            return (
              <li
                key={en}
                className={styles.step}
                data-state={index < step || last ? "done" : index === step ? "now" : "later"}
              >
                <Both ne={last ? ending[0] : ne} en={last ? ending[1] : en} />
              </li>
            );
          })}
        </ol>
      )}

      {current?.needs_media && !verdict && (
        <p className={styles.error}>
          <Both
            ne="हामी लिंक खोल्न सकेनौं (पोस्ट निजी वा हटाइएको हुन सक्छ)। कृपया फोटो वा भिडियो जोडेर बायाँबाट फेरि पठाउनुहोस्।"
            en="We could not open the link (the post may be private or deleted). Please send it again from the form with the photo or video attached."
          />
        </p>
      )}

      {verdict && (
        <>
          <p className={styles.verdictLabel} data-label={verdict.label}>
            {labelName[verdict.label].ne} <span lang="en">{labelName[verdict.label].en}</span>
          </p>
          <p className={styles.rationale}>{verdict.rationale_ne}</p>
          <p className={styles.rationaleEn} lang="en">
            {verdict.rationale_en}
          </p>
          {verdict.sources.length > 0 && (
            <div className={styles.sources}>
              <h2 className={styles.heading}>
                <Both ne="स्रोतहरू" en="Sources" />
              </h2>
              <ul className={styles.list}>
                {verdict.sources.map((source) => (
                  <li key={source.url}>
                    <a href={source.url} target="_blank" rel="noreferrer">
                      {source.name}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className={styles.quiet}>
            <Both
              ne={`तथ्य जाँचकर्ताहरूले प्रकाशित गरेको: ${new Date(verdict.published_at).toLocaleString("ne-NP")}`}
              en={`Published ${new Date(verdict.published_at).toLocaleString("en-GB")} by the fact-checkers.`}
            />
          </p>
        </>
      )}
    </article>
  );
}

function Mine({
  raw,
  selected,
  onOpen,
}: {
  raw: string;
  selected: string | null;
  onOpen: (id: string) => void;
}) {
  const [found, setFound] = useState<Record<string, PublicCase>>({});

  // Keyed on the raw string: a parsed array would be a new dependency on every render.
  useEffect(() => {
    parseMine(raw).forEach((id) =>
      site.case(id).then(
        (item) => setFound((all) => ({ ...all, [id]: item })),
        () => undefined,
      ),
    );
  }, [raw, selected]);

  const others = parseMine(raw).filter((id) => id !== selected);
  if (others.length === 0) return null;
  return (
    <section className={styles.group} aria-labelledby="mine">
      <h2 id="mine" className={styles.heading}>
        <Both ne="तपाईंले पठाएका" en="Sent from this browser" />
      </h2>
      <ul className={styles.list}>
        {others.map((id) => {
          const item = found[id];
          const label = item?.verdict?.label;
          return (
            <li key={id}>
              <button type="button" className={styles.item} onClick={() => onOpen(id)}>
                <span className={styles.itemId} lang="en">
                  {id}
                </span>
                {label ? (
                  <span className={styles.pill} data-label={label}>
                    {labelName[label].ne} <span lang="en">{labelName[label].en}</span>
                  </span>
                ) : item ? (
                  <span className={styles.quiet}>
                    {shortStatus[item.status][0]} <span lang="en">{shortStatus[item.status][1]}</span>
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Recent({ selected, onOpen }: { selected: string | null; onOpen: (id: string) => void }) {
  const [recent, setRecent] = useState<PublicCase[]>([]);

  useEffect(() => {
    site.verdicts().then(setRecent, () => setRecent([]));
  }, []);

  const shown = recent.filter((item) => item.verdict && item.id !== selected).slice(0, 10);
  if (shown.length === 0) return null;
  return (
    <section className={styles.group} aria-labelledby="recent">
      <h2 id="recent" className={styles.heading}>
        <Both ne="भर्खरै जाँचिएका" en="Recently checked" />
      </h2>
      <ul className={styles.list}>
        {shown.map((item) =>
          item.verdict ? (
            <li key={item.id}>
              <button type="button" className={styles.item} onClick={() => onOpen(item.id)}>
                <span className={styles.pill} data-label={item.verdict.label}>
                  {labelName[item.verdict.label].ne}{" "}
                  <span lang="en">{labelName[item.verdict.label].en}</span>
                </span>
                <span className={styles.itemText}>{item.verdict.rationale_ne}</span>
              </button>
            </li>
          ) : null,
        )}
      </ul>
    </section>
  );
}
