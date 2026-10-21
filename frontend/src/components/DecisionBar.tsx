"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ApiError, desk, type Decision, type DeskCase, type Label } from "@/lib/api";
import { useQueue } from "@/lib/queue";
import { useChecker } from "@/lib/session";
import { labelName } from "@/lib/words";
import styles from "./DecisionBar.module.css";

const LABELS: Label[] = ["false", "misleading", "true", "unverifiable"];

export function DecisionBar({ found, onDecided }: { found: DeskCase; onDecided: (c: DeskCase) => void }) {
  const { token, name } = useChecker();
  const { items, refresh, announce } = useQueue();
  const router = useRouter();
  const draft = found.outputs?.verdict ?? null;

  const [label, setLabel] = useState<Label | "">(draft?.label ?? "");
  const [editing, setEditing] = useState(!draft);
  const [rationaleEn, setRationaleEn] = useState(draft?.rationale_en ?? "");
  const [rationaleNe, setRationaleNe] = useState(draft?.rationale_ne ?? "");
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const [original, setOriginal] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function send(decision: Decision, done: string) {
    setBusy(true);
    setFailure(null);
    try {
      const updated = await desk.decide(token, found.id, decision);
      await refresh();
      announce(`${done}: ${found.claim_en ?? found.text ?? found.id}`);
      onDecided(updated);
      const next = items?.find((item) => item.id !== found.id);
      if (next && decision.action !== "reopen") router.push(`/desk/${next.id}`);
    } catch (caught) {
      setFailure(caught instanceof ApiError ? caught.message : "The decision was not saved. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const refuting = label === "false" || label === "misleading";

  function publish(event: FormEvent) {
    event.preventDefault();
    if (!label) return;
    const edited = rationaleEn !== draft?.rationale_en || rationaleNe !== draft?.rationale_ne;
    send(
      {
        action: "publish",
        checker: name,
        label,
        ...(edited ? { rationale_en: rationaleEn, rationale_ne: rationaleNe } : {}),
        ...(refuting && original.trim() ? { original_url: original.trim() } : {}),
      },
      `Published as ${labelName[label].en.toLowerCase()}`,
    );
  }

  if (found.status === "published" || found.status === "rejected") {
    const last = found.events.at(-1);
    return (
      <form
        className={styles.bar}
        onSubmit={(event) => {
          event.preventDefault();
          send({ action: "reopen", checker: name, note: note || "reopened" }, "Reopened");
        }}
      >
        <div className={styles.actions}>
          <p className={styles.closed}>
            {found.status === "published" && found.final_label
              ? `Published as ${labelName[found.final_label].en.toLowerCase()}`
              : "Rejected"}
            {last && ` by ${last.actor}`}
          </p>
          <input
            className={styles.note}
            placeholder="Why reopen? (new evidence, a correction)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            aria-label="Reason for reopening"
          />
          <button className={styles.secondary} disabled={busy}>
            {busy ? "Reopening…" : "Reopen"}
          </button>
          {failure && <p className={styles.failure} role="alert">{failure}</p>}
        </div>
      </form>
    );
  }

  if (found.status !== "routed") return null;

  if (rejecting) {
    return (
      <form
        className={styles.bar}
        onSubmit={(event) => {
          event.preventDefault();
          send({ action: "reject", checker: name, note }, "Rejected");
        }}
      >
        <div className={styles.actions}>
          <input
            className={styles.note}
            placeholder="Why reject? This goes in the case history."
            value={note}
            onChange={(e) => setNote(e.target.value)}
            required
            autoFocus
            aria-label="Reason for rejecting"
          />
          <button className={styles.danger} disabled={busy || !note.trim()}>
            {busy ? "Rejecting…" : "Reject case"}
          </button>
          <button type="button" className={styles.link} onClick={() => setRejecting(false)}>
            Cancel
          </button>
          {failure && <p className={styles.failure} role="alert">{failure}</p>}
        </div>
      </form>
    );
  }

  return (
    <form className={styles.bar} onSubmit={publish}>
      {editing && (
        <div className={styles.editor}>
          <label>
            Rationale in English
            <textarea value={rationaleEn} onChange={(e) => setRationaleEn(e.target.value)} rows={3} required />
          </label>
          <label>
            Rationale in Nepali
            <textarea
              lang="ne"
              value={rationaleNe}
              onChange={(e) => setRationaleNe(e.target.value)}
              rows={3}
              required
            />
          </label>
        </div>
      )}
      <div className={styles.actions}>
        <label className={styles.labelPick}>
          <span className="visually-hidden">Verdict</span>
          <select value={label} onChange={(e) => setLabel(e.target.value as Label)} required data-label={label}>
            <option value="" disabled>
              Choose a verdict
            </option>
            {LABELS.map((option) => (
              <option key={option} value={option}>
                {labelName[option].en}
              </option>
            ))}
          </select>
        </label>
        {refuting && (
          <input
            className={styles.note}
            type="url"
            inputMode="url"
            placeholder="Original found at (link, optional)"
            value={original}
            onChange={(e) => setOriginal(e.target.value)}
            aria-label="Link to the original footage, so Hamsa recognises its reposts"
          />
        )}
        <button className={styles.primary} disabled={busy || !label}>
          {busy ? "Publishing…" : label ? `Publish as ${labelName[label].en.toLowerCase()}` : "Publish"}
        </button>
        {draft && (
          <button type="button" className={styles.link} onClick={() => setEditing(!editing)}>
            {editing ? "Use the draft wording" : "Edit wording"}
          </button>
        )}
        <button type="button" className={styles.link} onClick={() => setRejecting(true)}>
          Reject
        </button>
        {failure && <p className={styles.failure} role="alert">{failure}</p>}
      </div>
    </form>
  );
}
