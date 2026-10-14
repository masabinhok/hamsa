import type { ReactNode } from "react";
import styles from "../app/site.module.css";

// Public pages lead in Nepali; English follows, smaller, for everyone else.
export function Both({ ne, en }: { ne: ReactNode; en: ReactNode }) {
  return (
    <>
      <span>{ne}</span>
      <span lang="en" className={styles.en}>
        {en}
      </span>
    </>
  );
}
