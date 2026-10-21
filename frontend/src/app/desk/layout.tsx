"use client";

import Link from "next/link";
import { Queue } from "@/components/Queue";
import { SignIn } from "@/components/SignIn";
import { QueueProvider, useQueue } from "@/lib/queue";
import { CheckerProvider, signOut, useStoredChecker } from "@/lib/session";
import styles from "./desk.module.css";

export default function DeskLayout({ children }: LayoutProps<"/desk">) {
  const checker = useStoredChecker();
  if (!checker) return <SignIn />;

  return (
    <CheckerProvider checker={checker}>
      <QueueProvider>
        <div className={styles.desk}>
          <aside className={styles.side}>
            <header className={styles.masthead}>
              <span className={styles.brand}>Hamsa</span>
              <span className={styles.who}>
                <Link href="/" className={styles.signOut}>
                  Public site
                </Link>
                {checker.name}
                <button type="button" className={styles.signOut} onClick={signOut}>
                  Sign out
                </button>
              </span>
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
