"use client";

import { useCallback, useEffect, useState } from "react";
import { desk, type ArchiveHit, type DeskCase, type Passage, type Verdict } from "@/lib/api";
import { useChecker } from "@/lib/session";
import { describeEvent, labelName, sentence } from "@/lib/words";
import { AuthedMedia } from "./AuthedMedia";
import { DecisionBar } from "./DecisionBar";
import styles from "./CaseView.module.css";

const DEVANAGARI = /[ऀ-ॿ]/;
const PENDING_POLL_MS = 3000;

function lang(text: string): "ne" | "en" {
  return DEVANAGARI.test(text) ? "ne" : "en";
}

export function CaseView({ id }: { id: string }) {
  const { token } = useChecker();
  const [found, setFound] = useState<DeskCase | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setFound(await desk.case(token, id));
      setError(null);
    } catch {
      setError("This case could not be loaded.");
    }
  }, [token, id]);

  useEffect(() => {
    const first = setTimeout(load, 0);
    return () => clearTimeout(first);
  }, [load]);

  const pending = found?.status === "received" || found?.status === "processing";
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(load, PENDING_POLL_MS);
    return () => clearInterval(timer);
  }, [pending, load]);

  if (error) return <p className={styles.notice}>{error}</p>;
  const current = found;
  if (!current) return <p className={styles.notice}>Loading the case…</p>;
  if (pending) {
    return (
      <p className={styles.notice}>
        The pipeline is still working on this post. It usually takes under a minute.
      </p>
    );
  }

  const outputs = current.outputs;
  const claim = outputs?.claim;
  const verdict = outputs?.verdict ?? null;
  const passages = outputs?.evidence?.passages ?? [];
  const hits = outputs?.media_match?.hits ?? [];

  return (
    <article className={styles.case}>
      <div className={styles.body}>
        <header className={styles.claimBlock}>
          {claim ? (
            <>
              <blockquote className={styles.claim} lang={lang(claim.claim)}>
                {claim.claim}
              </blockquote>
              {claim.claim_en !== claim.claim && <p className={styles.claimEn}>{claim.claim_en}</p>}
            </>
          ) : (
            <blockquote className={styles.claim} lang={lang(current.text ?? "")}>
              {current.text ?? "No claim could be read from this post."}
            </blockquote>
          )}
          <p className={styles.caseMeta}>
            Submitted {new Date(current.created_at).toLocaleString("en-GB")}
            {current.source_url && (
              <>
                {", from "}
                <a href={current.source_url} target="_blank" rel="noreferrer">
                  the original post
                </a>
              </>
            )}
          </p>
        </header>

        <section className={styles.section} aria-labelledby="why">
          <h2 id="why" className={styles.heading}>
            Why it is here
          </h2>
          <ul className={styles.reasons}>
            {current.reasons.map((reason) => (
              <li key={reason}>{sentence(reason)}</li>
            ))}
          </ul>
          {outputs?.failures.map((failure) => (
            <p key={failure.stage} className={styles.failure}>
              The {failure.stage.replace("_", " ")} step failed: {failure.error}
            </p>
          ))}
        </section>

        {verdict && <DraftVerdict verdict={verdict} />}

        {(current.media.length > 0 || hits.length > 0) && (
          <section className={styles.section} aria-labelledby="media">
            <h2 id="media" className={styles.heading}>
              The post&rsquo;s media
            </h2>
            <div className={styles.mediaGrid}>
              <div className={styles.mediaColumn}>
                {current.media.map((name) => (
                  <AuthedMedia key={name} caseId={current.id} name={name} />
                ))}
              </div>
              <div className={styles.mediaColumn}>
                {hits.length === 0 ? (
                  <p className={styles.quiet}>No match in the archive of known footage.</p>
                ) : (
                  hits.slice(0, 3).map((hit) => <ArchiveMatch key={hit.archive_id} hit={hit} />)
                )}
              </div>
            </div>
          </section>
        )}

        {claim && <ReadFromPost claim={claim} />}

        <Evidence passages={passages} verdict={verdict} />

        <section className={styles.section} aria-labelledby="history">
          <h2 id="history" className={styles.heading}>
            History
          </h2>
          <ol className={styles.history}>
            {current.events.map((event, index) => (
              <li key={index}>
                <time dateTime={event.at}>{new Date(event.at).toLocaleTimeString("en-GB")}</time>
                <span>
                  {describeEvent(event.to_status, event.note)}
                  {event.actor !== "system" && <span className={styles.actor}> by {event.actor}</span>}
                </span>
              </li>
            ))}
          </ol>
          {current.seconds && (
            <p className={styles.quiet}>
              Processed in {Object.values(current.seconds).reduce((a, b) => a + b, 0).toFixed(1)} s
            </p>
          )}
        </section>
      </div>

      <DecisionBar found={current} onDecided={setFound} />
    </article>
  );
}

function DraftVerdict({ verdict }: { verdict: Verdict }) {
  const name = labelName[verdict.label];
  return (
    <section className={styles.section} aria-labelledby="draft">
      <h2 id="draft" className={styles.heading}>
        Draft verdict
      </h2>
      <p className={styles.verdictLine}>
        <span className={styles.verdictLabel} data-label={verdict.label}>
          {name.en} <span lang="ne">{name.ne}</span>
        </span>
        <span className={styles.confidence}>{Math.round(verdict.confidence * 100)}% confident</span>
      </p>
      <p className={styles.rationale}>{verdict.rationale_en}</p>
      <p className={styles.rationale} lang="ne">
        {verdict.rationale_ne}
      </p>
      <p className={styles.quiet}>
        Drafted by {verdict.model}
        {verdict.fallback && ", the local fallback model, because the main model was unavailable"}.
      </p>
    </section>
  );
}

function ArchiveMatch({ hit }: { hit: ArchiveHit }) {
  const origin = hit.archive_label === "prior" ? "Older footage" : "Verified footage of this disaster";
  const closeness =
    hit.phash_distance !== null && hit.phash_distance <= 16
      ? `near-identical frame: ${hit.phash_distance} of 64 fingerprint bits differ`
      : `visually similar: ${Math.round((hit.cosine ?? 0) * 100)}% similarity`;
  return (
    <div className={styles.match} data-archive={hit.archive_label}>
      <p className={styles.matchTitle}>{origin}</p>
      <p>{hit.original_context}</p>
      <p className={styles.quiet}>{closeness}</p>
      <a href={hit.source_url} target="_blank" rel="noreferrer">
        Open the original
      </a>
    </div>
  );
}

function ReadFromPost({ claim }: { claim: NonNullable<DeskCase["outputs"]>["claim"] & object }) {
  const rows: [string, string[]][] = [
    ["Places", claim.places],
    ["Numbers", claim.numbers.map((n) => `${n.value}${n.unit ? ` ${n.unit}` : ""} ${n.refers_to}`)],
    ["Text on screen", claim.visible_text],
    ["Logos and watermarks", claim.watermarks],
    ["Accounts", claim.handles],
  ];
  const filled = rows.filter(([, values]) => values.length > 0);
  if (filled.length === 0 && !claim.claimed_date) return null;
  return (
    <section className={styles.section} aria-labelledby="read">
      <h2 id="read" className={styles.heading}>
        Read from the post
      </h2>
      <dl className={styles.facts}>
        {claim.claimed_date && (
          <>
            <dt>Date claimed</dt>
            <dd>{claim.claimed_date}</dd>
          </>
        )}
        {filled.map(([term, values]) => (
          <div key={term} className={styles.fact}>
            <dt>{term}</dt>
            {values.map((value) => (
              <dd key={value} lang={lang(value)}>
                {value}
              </dd>
            ))}
          </div>
        ))}
      </dl>
    </section>
  );
}

function Evidence({ passages, verdict }: { passages: Passage[]; verdict: Verdict | null }) {
  const stances = new Map(verdict?.citations.map((c) => [c.passage_id, c.stance]));
  const cited = passages.filter((p) => stances.has(p.passage_id));
  const other = passages.filter((p) => !stances.has(p.passage_id));
  return (
    <section className={styles.section} aria-labelledby="evidence">
      <h2 id="evidence" className={styles.heading}>
        Evidence
      </h2>
      {passages.length === 0 && (
        <p className={styles.quiet}>Nothing in the trusted sources addresses this claim yet.</p>
      )}
      <ul className={styles.passages}>
        {cited.map((p) => (
          <PassageItem key={p.passage_id} passage={p} stance={stances.get(p.passage_id)} />
        ))}
      </ul>
      {other.length > 0 && (
        <details className={styles.more}>
          <summary>
            {other.length} more {other.length === 1 ? "passage" : "passages"} found but not cited
          </summary>
          <ul className={styles.passages}>
            {other.map((p) => (
              <PassageItem key={p.passage_id} passage={p} />
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function PassageItem({ passage, stance }: { passage: Passage; stance?: "supports" | "refutes" }) {
  const date = passage.published_at
    ? new Date(passage.published_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })
    : "undated";
  const kind = passage.source_kind === "fact_check" ? "fact-check" : passage.source_kind;
  return (
    <li className={styles.passage} data-stance={stance}>
      <p className={styles.passageSource}>
        {stance && <span className={styles.stance}>{stance === "refutes" ? "Refutes" : "Supports"} the claim</span>}
        <span>
          {passage.source}, {kind}, {date}
        </span>
      </p>
      {passage.title && (
        <p className={styles.passageTitle} lang={lang(passage.title)}>
          <a href={passage.url} target="_blank" rel="noreferrer">
            {passage.title}
          </a>
        </p>
      )}
      <p className={styles.passageText} lang={lang(passage.text)}>
        {passage.text.length > 420 ? `${passage.text.slice(0, 420)}…` : passage.text}
      </p>
    </li>
  );
}
