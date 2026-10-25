import Link from "next/link";
import type { ReactNode } from "react";
import { Mark } from "@/components/Mark";
import { chapters } from "./chapters";
import s from "./book.module.css";

const parts = [...new Set(chapters.map((c) => c.part))];

function Contents({ current }: { current?: string }) {
  return (
    <>
      {parts.map((part) => (
        <div key={part}>
          <h2 className={s.partName}>{part}</h2>
          <ol className={s.chapterList}>
            {chapters.map((c, i) =>
              c.part === part ? (
                <li key={c.slug}>
                  <Link href={`/about/${c.slug}`} aria-current={c.slug === current ? "page" : undefined}>
                    <span className={s.n}>{i + 1}</span>
                    {c.title}
                  </Link>
                </li>
              ) : null,
            )}
          </ol>
        </div>
      ))}
    </>
  );
}

// Every chapter page: the contents stay on the left so a reader always knows where they are.
export function Book({ current, children }: { current: string; children: ReactNode }) {
  return (
    <div className={s.book} lang="en">
      <nav className={s.rail} aria-label="The Hamsa Book">
        <Link href="/about" className={s.brand}>
          <Mark size={32} /> The Hamsa Book
        </Link>
        <Contents current={current} />
        <Link href="/" className={s.home}>
          ← Back to Hamsa
        </Link>
      </nav>
      <details className={s.mobileContents}>
        <summary>
          <Mark size={24} /> The Hamsa Book · contents
        </summary>
        <Contents current={current} />
        <Link href="/" className={s.home}>
          ← Back to Hamsa
        </Link>
      </details>
      <main className={s.main}>{children}</main>
    </div>
  );
}

export function Cover() {
  return (
    <div className={s.cover} lang="en">
      <header className={s.coverHead}>
        <Mark size={72} />
        <p className={s.eyebrow}>The Hamsa Book</p>
        <h1>
          How a fact-check desk learns to separate the milk from the water <span lang="ne">हंस</span>
        </h1>
        <p className={s.coverLede}>
          The story of Hamsa: why it was built after Nepal&apos;s August 2026 floods, how it checks a disaster post in
          about a minute, why a person always decides, and how well it has done on real posts. Ten short chapters,
          about twenty minutes.
        </p>
        <div className={s.coverActions}>
          <Link href={`/about/${chapters[0].slug}`} className={s.start}>
            Start reading →
          </Link>
          <Link href="/" className={s.home}>
            Back to Hamsa
          </Link>
        </div>
      </header>
      <nav className={s.coverContents} aria-label="Contents">
        <Contents />
      </nav>
    </div>
  );
}
