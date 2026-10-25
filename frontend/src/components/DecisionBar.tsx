"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ApiError, desk, type Decision, type DeskCase, type Label } from "@/lib/api";
import { matchesFilter, useLabelFilter, useQueue } from "@/lib/queue";
import { useChecker } from "@/lib/session";
import { labelName } from "@/lib/words";
import styles from "./DecisionBar.module.css";

const LABELS: Label[] = ["false", "misleading", "true", "unverifiable"];

export function DecisionBar({ found, onDecided }: { found: DeskCase; onDecided: (c: DeskCase) => void }) {
  const { token, name } = useChecker();
  const { items, refresh, announce } = useQueue();
  const { label: filter, query } = useLabelFilter();
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
  const [translating, setTranslating] = useState(false);
  const [translation, setTranslation] = useState<string | null>(null);
  // The English the Nepali was written from. Checkers write English only, so an edited
  // English must never be published beside the draft's old Nepali (Oct 22 feedback).
  const [nepaliOf, setNepaliOf] = useState(draft?.rationale_en ?? "");
  const stale = editing && rationaleEn.trim() !== nepaliOf.trim();

  async function translate() {
    setTranslating(true);
    setTranslation(null);
    try {
      const english = rationaleEn;
      const { nepali, issue } = await desk.translate(token, english);
      setRationaleNe(nepali);
      setNepaliOf(english);
      setTranslation(issue ? `Reread the Nepali: ${issue}` : "Translated. Read it once before publishing.");
    } catch (caught) {
      setTranslation(caught instanceof ApiError ? caught.message : "Translation failed; write the Nepali by hand.");
    } finally {
      setTranslating(false);
    }
  }

  async function send(decision: Decision, done: string) {
    setBusy(true);
    setFailure(null);
    try {
      const updated = await desk.decide(token, found.id, decision);
      await refresh();
      announce(`${done}: ${found.claim_en ?? found.text ?? found.id}`);
      onDecided(updated);
      // The next case stays inside the checker's filter, e.g. one true draft after another.
      const next = items?.find((item) => item.id !== found.id && matchesFilter(item, filter));
      if (next && decision.action !== "reopen") router.push(`/desk/${next.id}${query}`);
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
    if (stale) {
      if (!translating) translate();
      setFailure("The Nepali is being redone from your English. Read it, then publish.");
      return;
    }
    const edited = rationaleEn !== draft?.rationale_en || rationaleNe !== draft?.rationale_ne;
    if (draft && label !== draft.label && !edited) {
      // The draft argues for its own label; published beside another, it contradicts itself.
      setEditing(true);
      setFailure(`The draft explains why it is ${labelName[draft.label].en.toLowerCase()}. Rewrite the English for ${labelName[label].en.toLowerCase()}, then publish.`);
      return;
    }
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
          send({ action: "reopen", checker: name, note: note || "reopened" }, found.status === "published" ? "Reopened for correction" : "Reopened");
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
            placeholder={found.status === "published" ? "What was wrong? (kept in the history)" : "Why reopen? (new evidence)"}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            aria-label="Reason for reopening"
          />
          <button className={styles.secondary} disabled={busy}>
            {busy ? "Reopening…" : found.status === "published" ? "Correct this verdict" : "Reopen"}
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
            <textarea
              value={rationaleEn}
              onChange={(e) => setRationaleEn(e.target.value)}
              onBlur={() => stale && rationaleEn.trim() && !translating && translate()}
              rows={3}
              required
            />
          </label>
          <div className={styles.nepali}>
            <label>
              Rationale in Nepali
              <textarea
                lang="ne"
                value={rationaleNe}
                onChange={(e) => {
                  setRationaleNe(e.target.value);
                  setNepaliOf(rationaleEn); // written by hand: the checker owns it
                }}
                rows={3}
                required
              />
            </label>
            <button
              type="button"
              className={styles.link}
              onClick={translate}
              disabled={translating || !rationaleEn.trim()}
            >
              {translating ? "Translating…" : "Translate from the English"}
            </button>
            {translation && <p role="status">{translation}</p>}
          </div>
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
          <button
            type="button"
            className={styles.link}
            onClick={() => {
              if (editing) {
                // Back to the draft as it was, so no edit is published beside an old Nepali.
                setRationaleEn(draft.rationale_en);
                setRationaleNe(draft.rationale_ne);
                setNepaliOf(draft.rationale_en);
                setTranslation(null);
              }
              setEditing(!editing);
            }}
          >
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
