"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import type { DeskSummary, Route } from "@/lib/api";
import { useQueue } from "@/lib/queue";
import { labelName, routeGroup, routeOrder, timeAgo } from "@/lib/words";
import styles from "./Queue.module.css";

export function Queue() {
  const { items, error } = useQueue();
  const params = useParams<{ id?: string }>();
  const router = useRouter();
  const ordered = useMemo(() => items ?? [], [items]);

  // j / k move through the queue, as in mail clients; ignored while typing.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select") || event.metaKey || event.ctrlKey) return;
      if (event.key !== "j" && event.key !== "k") return;
      const index = ordered.findIndex((item) => item.id === params.id);
      const next = ordered[index + (event.key === "j" ? 1 : -1)] ?? ordered[0];
      if (next) router.push(`/desk/${next.id}`);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ordered, params.id, router]);

  const groups = routeOrder
    .map((route) => [route, ordered.filter((item) => item.route === route)] as const)
    .filter(([, group]) => group.length > 0);

  return (
    <nav className={styles.queue} aria-label="Case queue">
      {error && <p className={styles.error}>{error}</p>}
      {items === null && !error && <p className={styles.quiet}>Loading the queue…</p>}
      {items?.length === 0 && (
        <p className={styles.quiet}>
          Nothing waiting. New submissions appear here as soon as the pipeline routes them.
        </p>
      )}
      {groups.map(([route, group]) => (
        <section key={route} className={styles.group} data-route={route}>
          <h2 className={styles.heading}>
            {routeGroup[route]} <span className={styles.count}>{group.length}</span>
          </h2>
          <ol className={styles.list}>
            {group.map((item) => (
              <QueueItem key={item.id} item={item} route={route} current={item.id === params.id} />
            ))}
          </ol>
        </section>
      ))}
      <p className={styles.hint}>
        <kbd>j</kbd> <kbd>k</kbd> to move between cases
      </p>
    </nav>
  );
}

function QueueItem({ item, route, current }: { item: DeskSummary; route: Route; current: boolean }) {
  const title = item.claim_en ?? item.text ?? "Media without text";
  return (
    <li>
      <Link
        href={`/desk/${item.id}`}
        className={styles.item}
        aria-current={current ? "page" : undefined}
        data-route={route}
      >
        <span className={styles.claim}>{title}</span>
        <span className={styles.meta}>
          {item.proposed_label && (
            <span className={styles.label} data-label={item.proposed_label}>
              {labelName[item.proposed_label].en}
            </span>
          )}
          <span>{timeAgo(item.created_at)}</span>
          {item.media_count > 0 && <span>{item.media_count === 1 ? "1 file" : `${item.media_count} files`}</span>}
        </span>
      </Link>
    </li>
  );
}
