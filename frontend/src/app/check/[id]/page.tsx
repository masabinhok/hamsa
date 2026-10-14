"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, site, type CaseStatus, type PublicCase } from "@/lib/api";
import { Both } from "@/components/Both";
import { labelName } from "@/lib/words";
import styles from "../../site.module.css";

const POLL_MS = 5000;
const FINAL: CaseStatus[] = ["published", "rejected", "merged"];

const waiting: Record<CaseStatus, [string, string]> = {
  received: ["प्राप्त भयो। Hamsa ले पोस्ट पढ्दैछ।", "Received. Hamsa is reading the post."],
  processing: [
    "Hamsa ले पोस्ट पढ्दै र प्रमाण खोज्दैछ।",
    "Hamsa is reading the post and looking for evidence.",
  ],
  routed: ["एक तथ्य जाँचकर्ताले यसलाई हेर्दै हुनुहुन्छ।", "A fact-checker is reviewing it."],
  merged: [
    "यो पोस्ट पहिले नै कसैले पठाइसक्नुभएको छ। त्यही रिपोर्टमा जाँच भइरहेको छ।",
    "Someone already sent this post. It is being checked under that report.",
  ],
  rejected: [
    "तथ्य जाँचकर्ताहरूले निर्णय प्रकाशित गरेनन्: पोस्टमा जाँच्न मिल्ने तथ्यगत दाबी छैन।",
    "The fact-checkers did not publish a verdict: the post makes no factual claim they can check.",
  ],
  published: ["", ""],
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
    <main className={styles.page} lang="ne">
      <header className={styles.header}>
        <Link href="/" className={styles.brand}>
          Hamsa
        </Link>
        <p className={styles.quiet}>
          <Both
            ne={`रिपोर्ट नं. ${id}। पछि हेर्न यो पेज राख्नुहोस्।`}
            en={`Report ${id}. Keep this page to come back to it.`}
          />
        </p>
      </header>

      {missing && (
        <p role="alert">
          <Both ne="यो नम्बरको कुनै रिपोर्ट छैन।" en="There is no report with this number." />
        </p>
      )}
      {!missing && !current && <p className={styles.quiet}>लोड हुँदैछ… Loading…</p>}
      {current && !verdict && (
        <p className={styles.waiting} role="status">
          <Both ne={waiting[current.status][0]} en={waiting[current.status][1]} />
        </p>
      )}
      {current?.needs_media && !verdict && (
        <p className={styles.error}>
          हामी लिंक खोल्न सकेनौं (पोस्ट निजी वा हटाइएको हुन सक्छ)। कृपया फोटो वा भिडियो जोडेर{" "}
          <Link href="/">फेरि पठाउनुहोस्</Link>।
          <span lang="en" className={styles.en}>
            We could not open the link (the post may be private or deleted). Please{" "}
            <Link href="/">send it again</Link> with the photo or video attached.
          </span>
        </p>
      )}

      {verdict && (
        <article className={styles.verdict}>
          <p className={styles.label} data-label={verdict.label}>
            {labelName[verdict.label].ne} <span lang="en">· {labelName[verdict.label].en}</span>
          </p>
          <p className={styles.rationale}>{verdict.rationale_ne}</p>
          <p className={styles.rationale} lang="en">
            {verdict.rationale_en}
          </p>
          {verdict.sources.length > 0 && (
            <>
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
            </>
          )}
          <p className={styles.quiet}>
            <Both
              ne={`तथ्य जाँचकर्ताहरूले प्रकाशित गरेको: ${new Date(verdict.published_at).toLocaleString("ne-NP")}`}
              en={`Published ${new Date(verdict.published_at).toLocaleString("en-GB")} by the fact-checkers.`}
            />
          </p>
        </article>
      )}
    </main>
  );
}
