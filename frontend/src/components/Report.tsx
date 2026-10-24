"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, site, type CaseStatus, type PublicCase } from "@/lib/api";
import { Both } from "@/components/Both";
import { ACCEPT, MAX_FILES, MAX_FILES_NE, Masthead, Mine, Recent, shortStatus, steps } from "@/components/Site";
import { labelName } from "@/lib/words";
import styles from "../app/site.module.css";

const POLL_MS = 5000;
const FINAL: CaseStatus[] = ["published", "rejected", "merged"];

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

function when(iso: string, locale: string): string {
  return new Date(iso).toLocaleString(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

// One report on the right; every other report stays a click away on the left.
export function Report({ id }: { id: string }) {
  return (
    <div className={styles.site} lang="ne" data-open="">
      <Masthead />
      <aside className={styles.listPane} aria-label="Other reports · अरू रिपोर्ट">
        <Mine selected={id} compact />
        <Recent selected={id} compact />
      </aside>
      <section className={styles.statusPane} aria-label="Report · रिपोर्ट">
        <Status id={id} />
      </section>
    </div>
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
  const [copied, setCopied] = useState(false);
  const verdict = current?.verdict;
  const step = current ? reached[current.status] : -1;
  const ending = current ? endings[current.status] : undefined;

  // While a report is being checked, where it has got to matters most; once published,
  // the verdict leads and the tracking becomes history at the end.
  const tracking = current && (
    <section className={styles.section} aria-labelledby="tracking" aria-live="polite">
      <h2 id="tracking" className={styles.heading}>
        <Both ne="जाँच कहाँ पुग्यो" en="Where the check is" />
      </h2>
      <ol className={styles.steps}>
        {steps.map(([ne, en], index) => {
          const last = index === step && ending;
          const at = current.timeline.findLast((entry) => reached[entry.status] === index)?.at;
          return (
            <li
              key={en}
              className={styles.step}
              data-state={index < step || last || verdict ? "done" : index === step ? "now" : "later"}
            >
              <Both ne={last ? ending[0] : ne} en={last ? ending[1] : en} />
              {at && index <= step && (
                <span className={styles.stepTime} lang="en">
                  {when(at, "en-GB")}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );

  function copyLink() {
    navigator.clipboard.writeText(window.location.href).then(
      () => setCopied(true),
      () => undefined,
    );
  }

  return (
    <article className={styles.status}>
      <header className={styles.reportHead}>
        <p className={styles.quiet}>
          <Both
            ne={`रिपोर्ट नं. ${id}${current ? ` · ${when(current.created_at, "ne-NP")} मा पठाइएको` : ""}`}
            en={`Report ${id}${current ? ` · sent ${when(current.created_at, "en-GB")}` : ""}`}
          />
        </p>
        <button type="button" className={styles.copy} onClick={copyLink}>
          {copied ? "लिंक कपी भयो · Copied" : "लिंक कपी गर्नुहोस् · Copy link"}
        </button>
      </header>

      {missing && (
        <p className={styles.error} role="alert">
          <Both ne="यो नम्बरको कुनै रिपोर्ट छैन।" en="There is no report with this number." />
        </p>
      )}
      {!missing && !current && <p className={styles.quiet}>लोड हुँदैछ… Loading…</p>}

      {current && !verdict && (
        <p className={styles.chip} data-size="large">
          {shortStatus[current.status][0]} <span lang="en">{shortStatus[current.status][1]}</span>
        </p>
      )}

      {verdict && (
        <section className={styles.verdict} aria-label="Verdict · निर्णय">
          <h1 className={styles.verdictLabel} data-label={verdict.label}>
            {labelName[verdict.label].ne} <span lang="en">{labelName[verdict.label].en}</span>
          </h1>
          <p className={styles.rationale}>{verdict.rationale_ne}</p>
          <p className={styles.rationaleEn} lang="en">
            {verdict.rationale_en}
          </p>
          <p className={styles.quiet}>
            <Both
              ne={`तथ्य जाँचकर्ताहरूले प्रकाशित गरेको: ${when(verdict.published_at, "ne-NP")}`}
              en={`Published ${when(verdict.published_at, "en-GB")} by the fact-checkers.`}
            />
          </p>
        </section>
      )}

      {current?.needs_media && current.status === "routed" && <SendMedia id={current.id} />}

      {current?.merged_into && (
        <p className={styles.notice}>
          <Link href={`/check/${encodeURIComponent(current.merged_into)}`}>
            {verdict ? (
              <Both
                ne="यही पोस्ट पहिले जाँचिएको थियो। त्यो रिपोर्ट हेर्नुहोस्"
                en={`This post was checked before: see report ${current.merged_into}`}
              />
            ) : (
              <Both ne="पहिलेको रिपोर्ट हेर्नुहोस्" en={`Follow report ${current.merged_into} instead`} />
            )}
          </Link>
        </p>
      )}

      {!verdict && tracking}

      {current && (
        <section className={styles.section} aria-labelledby="post">
          <h2 id="post" className={styles.heading}>
            <Both ne="पठाइएको पोस्ट" en="The post as sent" />
          </h2>
          {current.text && <blockquote className={styles.post}>{current.text}</blockquote>}
          {current.source_url && (
            <a href={current.source_url} target="_blank" rel="noreferrer" lang="en" className={styles.link}>
              {current.source_url}
            </a>
          )}
          {verdict && verdict.media.length > 0 ? (
            <div className={styles.media}>
              {verdict.media.map((name) =>
                /\.(mp4|webm)$/i.test(name) ? (
                  <video key={name} src={site.mediaUrl(id, name)} controls preload="metadata" />
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element -- the API serves it; nothing to optimise
                  <img key={name} src={site.mediaUrl(id, name)} alt="पोस्टको फोटो · Photo from the post" />
                ),
              )}
            </div>
          ) : current.media_count > 0 && !current.merged_into ? (
            <p className={styles.quiet}>
              <Both
                ne={`${current.media_count} वटा फाइल जोडिएको। तथ्य जाँचकर्ताले हेरेपछि यहाँ देखिन्छ।`}
                en={`${current.media_count} file${current.media_count > 1 ? "s" : ""} attached, shown once a fact-checker has reviewed it.`}
              />
            </p>
          ) : null}
        </section>
      )}

      {verdict?.claim && (
        <section className={styles.section} aria-labelledby="claim">
          <h2 id="claim" className={styles.heading}>
            <Both ne="जाँचिएको दाबी" en="The claim that was checked" />
          </h2>
          <p className={styles.rationale}>{verdict.claim.claim}</p>
          <p className={styles.rationaleEn} lang="en">
            {verdict.claim.claim_en}
          </p>
          {(verdict.claim.places.length > 0 || verdict.claim.claimed_date) && (
            <p className={styles.quiet} lang="en">
              {[verdict.claim.places.join(", "), verdict.claim.claimed_date].filter(Boolean).join(" · ")}
            </p>
          )}
        </section>
      )}

      {verdict && verdict.earlier_footage.length > 0 && (
        <section className={styles.section} aria-labelledby="footage">
          <h2 id="footage" className={styles.heading}>
            <Both ne="यही दृश्य पहिले कहाँ देखियो" en="Where this footage appeared before" />
          </h2>
          <ul className={styles.list}>
            {verdict.earlier_footage.map((footage) => (
              <li key={footage.source_url} className={styles.card} lang="en">
                <span>{footage.original_context}</span>
                <span className={styles.quiet}>
                  {footage.archive_label === "verified_genuine" ? "Verified genuine" : "Earlier footage"}
                  {footage.original_date && ` · ${footage.original_date}`} ·{" "}
                  <a href={footage.source_url} target="_blank" rel="noreferrer">
                    Original
                  </a>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {verdict && verdict.sources.length > 0 && (
        <section className={styles.section} aria-labelledby="sources">
          <h2 id="sources" className={styles.heading}>
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
        </section>
      )}

      {verdict && tracking}
    </article>
  );
}

// The report page polls, so once this lands the steps move on by themselves.
function SendMedia({ id }: { id: string }) {
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<[string, string] | null>(null);

  async function send(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const files = form.getAll("files").filter((f) => f instanceof File && f.size > 0);
    if (files.length === 0 || files.length > MAX_FILES) {
      setError([`१ देखि ${MAX_FILES_NE} वटा फाइल जोड्नुहोस्।`, `Attach 1 to ${MAX_FILES} files.`]);
      return;
    }
    setState("sending");
    setError(null);
    try {
      await site.sendMedia(id, form);
      setState("sent");
    } catch (failure) {
      setState("idle");
      setError([
        "पठाउन सकिएन। फेरि प्रयास गर्नुहोस्।",
        `Could not send it: ${failure instanceof Error ? failure.message : "unknown error"}.`,
      ]);
    }
  }

  if (state === "sent") {
    return (
      <p className={styles.notice} role="status">
        <Both ne="पायौं। यही रिपोर्ट फेरि जाँच हुँदैछ।" en="Received. This report is being checked again." />
      </p>
    );
  }
  return (
    <form className={styles.form} onSubmit={send} aria-labelledby="needs-media">
      <p id="needs-media" className={styles.error}>
        <Both
          ne="हामी लिंक खोल्न सकेनौं (पोस्ट निजी वा हटाइएको हुन सक्छ)। पोस्टको फोटो वा भिडियो यहाँ जोड्नुहोस्।"
          en="We could not open the link (the post may be private or deleted). Attach the post's photo or video here."
        />
      </p>
      <label className={styles.field}>
        <Both ne="फोटो वा भिडियो" en={`Photo or video (up to ${MAX_FILES}, 100 MB each)`} />
        <input name="files" type="file" accept={ACCEPT} multiple required />
      </label>
      {error && (
        <p className={styles.error} role="alert">
          <Both ne={error[0]} en={error[1]} />
        </p>
      )}
      <button className={styles.submit} disabled={state === "sending"}>
        {state === "sending" ? "पठाउँदै… Sending…" : "पठाउनुहोस् · Send"}
      </button>
    </form>
  );
}
