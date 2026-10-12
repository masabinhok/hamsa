"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, site, type CaseStatus, type PublicCase } from "@/lib/api";
import { labelName } from "@/lib/words";
import styles from "../../site.module.css";

const POLL_MS = 5000;
const FINAL: CaseStatus[] = ["published", "rejected", "merged"];

const waiting: Record<CaseStatus, string> = {
  received: "Received. Hamsa is reading the post.",
  processing: "Hamsa is reading the post and looking for evidence.",
  routed: "A fact-checker is reviewing it.",
  merged: "Someone already sent this post. It is being checked under that report.",
  rejected: "The fact-checkers did not publish a verdict: the post makes no factual claim they can check.",
  published: "",
};

export default function Check() {
  const { id } = useParams<{ id: string }>();
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

  const verdict = current?.verdict;
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.brand}>
          Hamsa
        </Link>
        <p className={styles.quiet}>
          Report {id}. Keep this page to come back to it.
        </p>
      </header>

      {missing && <p role="alert">There is no report with this number.</p>}
      {!missing && !current && <p className={styles.quiet}>Loading…</p>}
      {current && !verdict && (
        <p className={styles.waiting} role="status">
          {waiting[current.status]}
        </p>
      )}

      {verdict && (
        <article className={styles.verdict}>
          <p className={styles.label} data-label={verdict.label}>
            <span lang="ne">{labelName[verdict.label].ne}</span> · {labelName[verdict.label].en}
          </p>
          <p className={styles.rationale} lang="ne">
            {verdict.rationale_ne}
          </p>
          <p className={styles.rationale}>{verdict.rationale_en}</p>
          {verdict.sources.length > 0 && (
            <>
              <h2 className={styles.heading}>Sources</h2>
              <ul className={styles.list}>
                {verdict.sources.map((source) => (
                  <li key={source.url}>
                    <a href={source.url} target="_blank" rel="noreferrer">
                      {source.name}
                    </a>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className={styles.quiet}>
            Published {new Date(verdict.published_at).toLocaleString("en-GB")} by the fact-checkers.
          </p>
        </article>
      )}
    </main>
  );
}
