"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { Mark } from "@/components/Mark";
import { Queue } from "@/components/Queue";
import { SignIn } from "@/components/SignIn";
import { QueueProvider, useQueue } from "@/lib/queue";
import { CheckerProvider, signOut, useStoredChecker } from "@/lib/session";
import styles from "./desk.module.css";

export default function DeskLayout({ children }: LayoutProps<"/desk">) {
  const checker = useStoredChecker();
  const atOverview = usePathname() === "/desk";
  if (!checker) return <SignIn />;

  // The queue filter reads the URL (useSearchParams), which Next wants inside a Suspense boundary.
  return (
    <Suspense fallback={null}>
    <CheckerProvider checker={checker}>
      <QueueProvider>
        <div className={styles.desk}>
          <aside className={styles.side}>
            <header className={styles.masthead}>
              <Link href="/desk" className={styles.brand} aria-label="Hamsa desk overview">
                <Mark size={24} /> Hamsa <span className={styles.brandDesk}>desk</span>
              </Link>
              <p className={styles.who}>
                Signed in as <strong>{checker.name}</strong>
              </p>
              <nav className={styles.deskNav} aria-label="Desk">
                <Link href="/desk" aria-current={atOverview ? "page" : undefined}>
                  Overview
                </Link>
                <Link href="/">Public site</Link>
                <button type="button" className={styles.signOut} onClick={signOut}>
                  Sign out
                </button>
              </nav>
            </header>
            <Queue />
          </aside>
          <main className={styles.main}>
            <Notice />
            {children}
          </main>
        </div>
      </QueueProvider>
    </CheckerProvider>
    </Suspense>
  );
}

// Always mounted, so screen readers hear each confirmation through the same live region.
function Notice() {
  const { notice } = useQueue();
  return (
    <p className={styles.notice} role="status" data-shown={notice.shown ? "" : undefined}>
      {notice.text}
    </p>
  );
}
