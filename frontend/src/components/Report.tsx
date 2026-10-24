"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, site, type CaseStatus, type PublicCase } from "@/lib/api";
import { Both } from "@/components/Both";
import { ACCEPT, MAX_FILES, MAX_FILES_NE, Masthead, Mine, Recent, Tag, shortStatus, steps } from "@/components/Site";
import { stanceName, timeAgoNe } from "@/lib/words";
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

// One report as the page, with the reader's own reports beside it and more checked posts below.
export function Report({ id }: { id: string }) {
  return (
    <div className={styles.site} lang="ne">
      <Masthead />
      <main className={styles.page}>
        <div className={styles.columns}>
          <Status id={id} />
          <aside className={styles.rail} aria-label="तपाईंका रिपोर्ट · Your reports">
            <Mine selected={id} />
          </aside>
        </div>
        <Recent selected={id} compact />
      </main>
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
  const [shared, setShared] = useState(false);
  const verdict = current?.verdict;
  const step = current ? reached[current.status] : -1;
  const ending = current ? endings[current.status] : undefined;

  // While a report is being checked, where it has got to matters most; once published,
  // the verdict is the article and the tracking becomes its history at the end.
  const tracking = current && (
    <section className={styles.section} aria-labelledby="tracking" aria-live="polite">
      <h2 id="tracking">
        <Both ne={verdict ? "जाँचको इतिहास" : "जाँच कहाँ पुग्यो"} en={verdict ? "How this check went" : "Where the check is"} />
      </h2>
      <ol className={styles.steps}>
        {steps.map(([ne, en], index) => {
          const last = index === step && ending;
          const at = current.timeline.findLast((entry) => reached[entry.status] === index)?.at;
          const state = index < step || last || verdict ? "done" : index === step ? "now" : "later";
          return (
            <li key={en} className={styles.step} data-state={state} aria-current={state === "now" ? "step" : undefined}>
              <Both ne={last ? ending[0] : ne} en={last ? ending[1] : en} />
              {at && index <= step && <span className={styles.stepTime}>{when(at, "ne-NP")}</span>}
            </li>
          );
        })}
      </ol>
    </section>
  );

  async function share() {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title: document.title, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setShared(true);
    } catch {
      // Cancelled, or no clipboard over plain http: the address bar still has the link.
    }
  }

  const shareButton = (
    <button type="button" className={styles.share} onClick={share}>
      {shared ? "लिंक कपी भयो · Copied" : "सेयर गर्नुहोस् · Share"}
    </button>
  );

  if (missing) {
    return (
      <p className={styles.error} role="alert">
        <Both ne="यो नम्बरको कुनै रिपोर्ट छैन।" en="There is no report with this number." />
      </p>
    );
  }
  if (!current) return <p className={styles.quiet}>लोड हुँदैछ… Loading…</p>;

  const post = (
    <section className={styles.section} aria-labelledby="post">
      <h2 id="post">
        <Both ne="पठाइएको पोस्ट" en="The post as sent" />
      </h2>
      {current.text && <blockquote className={styles.post}>{current.text}</blockquote>}
      {current.source_url && (
        <a href={current.source_url} target="_blank" rel="noreferrer" lang="en" className={styles.link}>
          {current.source_url}
        </a>
      )}
      {!verdict && current.media_count > 0 && !current.merged_into && (
        <p className={styles.quiet}>
          <Both
            ne={`${current.media_count} वटा फाइल जोडिएको। तथ्य जाँचकर्ताले हेरेपछि यहाँ देखिन्छ।`}
            en={`${current.media_count} file${current.media_count > 1 ? "s" : ""} attached, shown once a fact-checker has reviewed it.`}
          />
        </p>
      )}
    </section>
  );

  const merged = current.merged_into && (
    <p className={styles.notice}>
      <Link href={`/check/${encodeURIComponent(current.merged_into)}`}>
        {verdict ? (
          <Both ne="यही पोस्ट पहिले जाँचिएको थियो। त्यो रिपोर्ट हेर्नुहोस्" en={`This post was checked before: see report ${current.merged_into}`} />
        ) : (
          <Both ne="पहिलेको रिपोर्ट हेर्नुहोस्" en={`Follow report ${current.merged_into} instead`} />
        )}
      </Link>
    </p>
  );

  if (!verdict) {
    return (
      <article className={styles.article}>
        <header className={styles.articleHead}>
          <p className={styles.chip} data-size="large">
            {shortStatus[current.status][0]} <span lang="en">{shortStatus[current.status][1]}</span>
          </p>
          <h1 className={styles.headline}>
            <Both ne={`रिपोर्ट नं. ${id}`} en={`Report ${id}`} />
          </h1>
          <div className={styles.byline}>
            <span>
              <Both ne={`${when(current.created_at, "ne-NP")} मा पठाइएको`} en={`Sent ${when(current.created_at, "en-GB")}`} />
            </span>
            {shareButton}
          </div>
        </header>
        {current.needs_media && current.status === "routed" && <SendMedia id={current.id} />}
        {merged}
        {tracking}
        {post}
      </article>
    );
  }

  const claim = verdict.claim;
  const place = claim?.places.join(", ");
  return (
    <article className={styles.article} data-label={verdict.label}>
      <header className={styles.articleHead}>
        <Tag label={verdict.label} />
        <h1 className={styles.headline}>{claim?.claim ?? current.text ?? verdict.rationale_ne}</h1>
        {claim?.claim_en && claim.claim_en.trim() !== claim.claim.trim() && (
          <p className={styles.standfirst} lang="en">
            {claim.claim_en}
          </p>
        )}
        <div className={styles.byline}>
          <span>
            <strong>तथ्य जाँचकर्ताले प्रकाशित</strong> · {timeAgoNe(verdict.published_at)}
            {place && ` · ${place}`}
          </span>
          {shareButton}
        </div>
      </header>

      {verdict.media.length > 0 && (
        <figure className={styles.figure}>
          {verdict.media.map((name) =>
            /\.(mp4|webm)$/i.test(name) ? (
              <video key={name} src={site.mediaUrl(id, name)} controls preload="metadata" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element -- the API serves it; nothing to optimise
              <img key={name} src={site.mediaUrl(id, name)} alt="जाँचिएको पोस्टको फोटो · Photo from the checked post" />
            ),
          )}
          <figcaption>
            <Both ne="जाँचका लागि पठाइएको पोस्ट" en="The post that was sent for checking" />
          </figcaption>
        </figure>
      )}

      <div className={styles.body}>
        <p>{verdict.rationale_ne}</p>
      </div>

      <section className={styles.box} lang="en" aria-labelledby="in-english">
        <h2 id="in-english">In English</h2>
        <p className={styles.boxEn}>{verdict.rationale_en}</p>
      </section>

      {merged}

      {verdict.earlier_footage.length > 0 && (
        <section className={styles.section} aria-labelledby="footage">
          <h2 id="footage">
            <Both ne="यही दृश्य पहिले कहाँ देखियो" en="Where this footage appeared before" />
          </h2>
          <ul className={styles.sources}>
            {verdict.earlier_footage.map((footage) => (
              <li key={footage.source_url}>
                <span>{footage.original_context}</span>
                <span className={styles.stance}>
                  {footage.archive_label === "verified_genuine" ? "पुष्टि भएको दृश्य · Verified genuine" : "पहिलेको दृश्य · Earlier footage"}
                  {footage.original_date && ` · ${footage.original_date}`} ·{" "}
                  <a href={footage.source_url} target="_blank" rel="noreferrer">
                    मूल · Original
                  </a>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {verdict.sources.length > 0 && (
        <section className={styles.section} aria-labelledby="sources">
          <h2 id="sources">
            <Both ne="स्रोतहरू" en="Sources" />
          </h2>
          <ul className={styles.sources}>
            {verdict.sources.map((source) => (
              <li key={source.url}>
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.name}
                </a>
                <span className={styles.stance} data-stance={source.stance}>
                  {stanceName[source.stance].ne} · <span lang="en">{stanceName[source.stance].en}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className={styles.box} aria-labelledby="how">
        <h2 id="how">
          <Both ne="हामीले कसरी जाँच्यौं" en="How we checked" />
        </h2>
        <p>
          <Both
            ne="Hamsa ले पोस्टको दाबी र दृश्यहरू पढ्यो, पहिले जाँचिएका दृश्यहरूसँग मिलायो, र समाचार तथा तथ्य जाँचहरू खोज्यो। त्यसपछि तथ्य जाँचकर्ताले प्रमाण हेरेर यो निर्णय प्रकाशित गर्नुभयो।"
            en="Hamsa read the post's claim and frames, compared them with footage checked before, and searched news and fact-checks. A fact-checker then reviewed the evidence and published this verdict."
          />
        </p>
      </section>

      {claim && (
        <section className={styles.section} aria-labelledby="claim">
          <h2 id="claim">
            <Both ne="जाँचिएको दाबी" en="The claim that was checked" />
          </h2>
          <p>{claim.claim}</p>
          {claim.claim_en && <p className={styles.quiet} lang="en">{claim.claim_en}</p>}
          {claim.claimed_date && <p className={styles.quiet}>{claim.claimed_date}</p>}
        </section>
      )}

      {post}
      {tracking}
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
