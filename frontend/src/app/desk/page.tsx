"use client";

import Link from "next/link";
import { useQueue } from "@/lib/queue";
import styles from "./desk.module.css";

// What a new checker sees first: the whole job in three steps, then the first case.
export default function DeskHome() {
  const { items } = useQueue();
  const first = items?.[0];
  return (
    <section className={styles.guide} aria-labelledby="guide">
      <h1 id="guide" className={styles.guideTitle}>
        How the desk works
      </h1>
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
      {first ? (
        <Link href={`/desk/${first.id}`} className={styles.start}>
          Open the first case
        </Link>
      ) : (
        <p className={styles.quietLine}>No cases are waiting. New reports appear in the queue on the left.</p>
      )}
      <p className={styles.quietLine}>
        Keys: <kbd>j</kbd> next case, <kbd>k</kbd> previous case.
      </p>
    </section>
  );
}
