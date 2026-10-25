import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Book } from "../Book";
import { chapters } from "../chapters";
import s from "../book.module.css";

export const dynamicParams = false;

export function generateStaticParams() {
  return chapters.map((c) => ({ chapter: c.slug }));
}

export async function generateMetadata({ params }: PageProps<"/about/[chapter]">): Promise<Metadata> {
  const { chapter: slug } = await params;
  const chapter = chapters.find((c) => c.slug === slug);
  return chapter ? { title: `${chapter.title} · The Hamsa Book`, description: chapter.lede } : {};
}

export default async function ChapterPage({ params }: PageProps<"/about/[chapter]">) {
  const { chapter: slug } = await params;
  const index = chapters.findIndex((c) => c.slug === slug);
  if (index < 0) notFound();
  const chapter = chapters[index];
  const prev = chapters[index - 1];
  const next = chapters[index + 1];

  return (
    <Book current={slug}>
      <article className={s.chapter}>
        <header className={s.chapterHead}>
          <p className={s.eyebrow}>
            {chapter.part} · Chapter {index + 1}
          </p>
          <h1>{chapter.title}</h1>
          <p className={s.lede}>{chapter.lede}</p>
        </header>
        {chapter.body}
        <nav className={s.pager} aria-label="Chapters">
          {prev ? (
            <Link href={`/about/${prev.slug}`} rel="prev">
              <span>← Previous</span>
              {prev.title}
            </Link>
          ) : (
            <Link href="/about" rel="prev">
              <span>← Cover</span>
              The Hamsa Book
            </Link>
          )}
          {next ? (
            <Link href={`/about/${next.slug}`} rel="next" className={s.nextLink}>
              <span>Next →</span>
              {next.title}
            </Link>
          ) : (
            <Link href="/" rel="next" className={s.nextLink}>
              <span>The end →</span>
              Send Hamsa a post
            </Link>
          )}
        </nav>
      </article>
    </Book>
  );
}
