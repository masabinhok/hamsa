"use client";

import { useEffect, useRef, useState } from "react";
import { desk } from "@/lib/api";
import { useChecker } from "@/lib/session";
import styles from "./CaseView.module.css";

// Desk media needs the bearer token, which <img src> cannot send, so fetch it as a blob.
// `start` opens a video at the matched moment, so post and original can be compared.
// `searchable` adds reverse-image search: search engines cannot fetch desk media behind the
// login, so the checker copies the frame on screen and pastes it into the search page.
export function AuthedMedia({
  path,
  alt,
  start = null,
  searchable = false,
}: {
  path: string;
  alt: string;
  start?: number | null;
  searchable?: boolean;
}) {
  const { token } = useChecker();
  const videoRef = useRef<HTMLVideoElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [note, setNote] = useState("");
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

  async function copyFrame() {
    const source = videoRef.current ?? imageRef.current;
    if (!source) return;
    const video = source instanceof HTMLVideoElement;
    const canvas = document.createElement("canvas");
    canvas.width = video ? source.videoWidth : source.naturalWidth;
    canvas.height = video ? source.videoHeight : source.naturalHeight;
    canvas.getContext("2d")?.drawImage(source, 0, 0);
    try {
      const png = await new Promise<Blob>((resolve, reject) =>
        canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("no frame"))), "image/png"),
      );
      await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
      setNote("Frame copied. Open a search page and paste it (Ctrl+V).");
    } catch {
      setNote("The browser blocked copying. Right-click the frame and copy the image instead.");
    }
  }

  if (failed) return <p className={styles.quiet}>This file could not be loaded.</p>;
  if (!media)
    return (
      <div className={styles.mediaPlaceholder} role="status">
        <span className="visually-hidden">Loading media</span>
      </div>
    );
  const player = media.video ? (
    <video
      ref={videoRef}
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
    <img ref={imageRef} className={styles.media} src={media.url} alt={alt} />
  );
  if (!searchable) return player;
  return (
    <div className={styles.mediaColumn}>
      {player}
      <div className={styles.frameSearch}>
        <button type="button" onClick={copyFrame}>
          Copy this frame
        </button>
        <span>then search it on</span>
        <a href="https://lens.google.com/" target="_blank" rel="noreferrer">
          Google Lens
        </a>
        <a href="https://yandex.com/images/" target="_blank" rel="noreferrer">
          Yandex
        </a>
        <a href="https://tineye.com/" target="_blank" rel="noreferrer">
          TinEye
        </a>
        <span role="status" className={styles.quiet}>
          {note}
        </span>
      </div>
    </div>
  );
}
