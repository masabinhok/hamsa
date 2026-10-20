"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { site, type PublicCase, type Route } from "@/lib/api";
import { useQueue } from "@/lib/queue";
import { labelName, reasonTag, routeGroup, routeOrder, timeAgo } from "@/lib/words";
import styles from "./desk.module.css";

const NEXT_UP = 5;
const RECENT = 8;

const routeHint: Partial<Record<Route, string>> = {
  fast_track: "Strong evidence. Confirm the draft and publish.",
  human_review: "Evidence is mixed or thin.",
  investigate: "Nothing known yet. Start from the post.",
  dismiss: "Probably no factual claim.",
};

// What a checker sees first: what is waiting, what to open next, and what went out lately.
export default function DeskHome() {
  const { items } = useQueue();
  const [published, setPublished] = useState<PublicCase[] | null>(null);

  useEffect(() => {
    site.verdicts().then(setPublished, () => setPublished([]));
  }, []);

  const queue = items ?? [];
  return (
    <div className={styles.overview}>
      <header className={styles.overviewHead}>
        <h1 className={styles.guideTitle}>Desk overview</h1>
        {queue[0] && (
          <Link href={`/desk/${queue[0].id}`} className={styles.start}>
            Open the next case
          </Link>
        )}
      </header>

      <section className={styles.tiles} aria-label="Waiting cases">
        {routeOrder.map((route) => {
          const waiting = queue.filter((item) => item.route === route);
          const body = (
            <>
              <span className={styles.tileCount}>{items ? waiting.length : "–"}</span>
              <span className={styles.tileName}>{routeGroup[route]}</span>
              <span className={styles.quietLine}>{routeHint[route]}</span>
            </>
          );
          return waiting[0] ? (
            <Link key={route} href={`/desk/${waiting[0].id}`} className={styles.tile} data-route={route}>
              {body}
            </Link>
          ) : (
            <div key={route} className={styles.tile} data-route={route}>
              {body}
            </div>
          );
        })}
      </section>

      {items?.length === 0 && (
        <p className={styles.clear}>
          Queue clear. New reports land here as soon as Hamsa has read them. To try the desk, send a test
          post from the <Link href="/">public site</Link>.
        </p>
      )}

      <div className={styles.columns}>
        {queue.length > 0 && (
          <section className={styles.panel} aria-labelledby="next">
            <h2 id="next" className={styles.panelTitle}>
              Next up
            </h2>
            <ol className={styles.rows}>
              {queue.slice(0, NEXT_UP).map((item) => (
                <li key={item.id}>
                  <Link href={`/desk/${item.id}`} className={styles.row}>
                    <span className={styles.rowTitle}>{item.claim_en ?? item.text ?? "Media without text"}</span>
                    <span className={styles.rowMeta}>
                      {item.route && <span>{routeGroup[item.route]}</span>}
                      {item.proposed_label && (
                        <span data-label={item.proposed_label}>Draft: {labelName[item.proposed_label].en}</span>
                      )}
                      {reasonTag(item.reasons) && <span>{reasonTag(item.reasons)}</span>}
                      <span>{timeAgo(item.created_at)}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          </section>
        )}

        <section className={styles.panel} aria-labelledby="published">
          <h2 id="published" className={styles.panelTitle}>
            Recently published
          </h2>
          {published?.length === 0 && <p className={styles.quietLine}>Nothing published yet.</p>}
          <ol className={styles.rows}>
            {published?.slice(0, RECENT).map((item) =>
              item.verdict ? (
                <li key={item.id}>
                  <Link href={`/desk/${item.id}`} className={styles.row}>
                    <span className={styles.rowTitle}>
                      {item.verdict.claim?.claim_en ?? item.text ?? item.verdict.rationale_en}
                    </span>
                    <span className={styles.rowMeta}>
                      <span data-label={item.verdict.label}>{labelName[item.verdict.label].en}</span>
                      <span>{timeAgo(item.verdict.published_at)}</span>
                    </span>
                  </Link>
                </li>
              ) : null,
            )}
          </ol>
        </section>
      </div>

      <details className={styles.guide} open={items?.length === 0}>
        <summary className={styles.panelTitle}>How the desk works</summary>
        <ol className={styles.steps}>
          <li>
            <strong>Cases arrive sorted.</strong> <em>Quick check</em>: Hamsa found strong evidence
            (recycled footage, a matching fact-check, or several news reports). <em>Needs a checker</em>:
            the evidence is mixed or thin. <em>New claims</em>: nothing known yet. The tag on each case
            says why it is there.
          </li>
          <li>
            <strong>Read a case left to right.</strong> Left is the post, with any earlier copy of its
            footage beside it. Right is Hamsa&rsquo;s draft verdict and the sources it relied on.
            Always ask: does the cited source talk about <em>this exact</em> claim?
          </li>
          <li>
            <strong>Decide.</strong> Publish the draft, edit its wording, change the label, or reject. If
            you found the original footage (Copy this frame, then Google Lens), paste its link: Hamsa will
            recognise every repost of it from then on.
          </li>
        </ol>
        <p className={styles.quietLine}>
          Keys: <kbd>j</kbd> next case, <kbd>k</kbd> previous case.
        </p>
      </details>
    </div>
  );
}
