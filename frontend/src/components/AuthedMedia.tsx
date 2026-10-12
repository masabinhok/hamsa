"use client";

import { useEffect, useState } from "react";
import { desk } from "@/lib/api";
import { useChecker } from "@/lib/session";
import styles from "./CaseView.module.css";

// Desk media needs the bearer token, which <img src> cannot send, so fetch it as a blob.
// `start` opens a video at the matched moment, so post and original can be compared.
export function AuthedMedia({
  path,
  alt,
  start = null,
}: {
  path: string;
  alt: string;
  start?: number | null;
}) {
  const { token } = useChecker();
  const [media, setMedia] = useState<{ url: string; video: boolean } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    desk
      .file(token, path)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setMedia({ url, video: blob.type.startsWith("video/") });
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [token, path]);

  if (failed) return <p className={styles.quiet}>This file could not be loaded.</p>;
  if (!media) return <div className={styles.mediaPlaceholder} aria-label="Loading media" />;
  return media.video ? (
    <video
      className={styles.media}
      src={media.url}
      controls
      preload="metadata"
      aria-label={alt}
      onLoadedMetadata={(event) => {
        if (start) event.currentTarget.currentTime = start;
      }}
    />
  ) : (
    // eslint-disable-next-line @next/next/no-img-element -- a blob URL, not an optimisable asset
    <img className={styles.media} src={media.url} alt={alt} />
  );
}
