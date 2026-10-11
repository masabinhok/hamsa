"use client";

import { Queue } from "@/components/Queue";
import { SignIn } from "@/components/SignIn";
import { QueueProvider } from "@/lib/queue";
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
                {checker.name}
                <button type="button" className={styles.signOut} onClick={signOut}>
                  Sign out
                </button>
              </span>
            </header>
            <Queue />
          </aside>
          <main className={styles.main}>{children}</main>
        </div>
      </QueueProvider>
    </CheckerProvider>
  );
}
