// Interface vocabulary in one place, so an action keeps its name everywhere.
import type { Label, Route, Stance } from "./api";

export const routeGroup: Record<Route, string> = {
  // Strong evidence, but still a draft: a checker confirms before anything is published.
  fast_track: "Quick check",
  human_review: "Needs a checker",
  investigate: "New claims",
  dismiss: "Not a factual claim",
  merge: "Merged",
};

export const routeOrder: Route[] = ["fast_track", "human_review", "investigate", "dismiss"];

export const labelName: Record<Label, { en: string; ne: string }> = {
  false: { en: "False", ne: "गलत" },
  misleading: { en: "Misleading", ne: "भ्रामक" },
  true: { en: "True", ne: "सत्य" },
  unverifiable: { en: "Unverifiable", ne: "पुष्टि हुन नसकेको" },
};

// Why the router put a case where it is, in two or three words for the queue.
export function reasonTag(reasons: string[]): string | null {
  const first = reasons[0]?.toLowerCase() ?? "";
  const tags: [string, string][] = [
    ["recycled media", "Recycled footage"],
    ["prior fact-check agrees", "Fact-check agrees"],
    ["strong evidence", "News confirms"],
    ["visible ai-tool watermark", "AI watermark"],
    ["nepali rationale", "Check the Nepali"],
    ["new claim", "Nothing known yet"],
    ["drafted by the local fallback", "Backup model draft"],
    ["failed", "Step failed"],
    ["cited", "Sources disagree"],
    ["ambiguous", "Evidence unclear"],
  ];
  return tags.find(([start]) => first.includes(start))?.[1] ?? null;
}

export function timeAgo(iso: string, now = Date.now()): string {
  const minutes = Math.round((now - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

const neNumber = new Intl.NumberFormat("ne-NP");

/** "७ मिनेट अगाडि", the way Nepali news sites date a story; older ones get a Nepali date. */
export function timeAgoNe(iso: string, now = Date.now()): string {
  const minutes = Math.round((now - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "भर्खरै";
  if (minutes < 60) return `${neNumber.format(minutes)} मिनेट अगाडि`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${neNumber.format(hours)} घण्टा अगाडि`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${neNumber.format(days)} दिन अगाडि`;
  return new Date(iso).toLocaleDateString("ne-NP", { day: "numeric", month: "long", year: "numeric" });
}

export const stanceName: Record<Stance, { en: string; ne: string }> = {
  supports: { en: "Supports the claim", ne: "दाबीलाई समर्थन" },
  refutes: { en: "Refutes the claim", ne: "दाबीको खण्डन" },
};

export function sentence(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const statusWords: Record<string, string> = {
  received: "Submitted",
  processing: "Checked by the pipeline",
  routed: "Sent to the desk",
  merged: "Merged into an earlier case",
  published: "Published",
  rejected: "Rejected",
};

/** One line of case history in plain words, e.g. "Sent to the desk as ready to publish". */
export function describeEvent(toStatus: string, note: string | null): string {
  const action = statusWords[toStatus] ?? sentence(toStatus);
  if (!note) return action;
  if (toStatus === "received") return sentence(note); // "submitted via web"
  // System routing notes look like "fast_track: reason; reason".
  const [prefix, ...rest] = note.split(": ");
  if (toStatus === "routed" && prefix in routeGroup && rest.length > 0) {
    return `${action} as ${routeGroup[prefix as Route].toLowerCase()}. ${sentence(rest.join(": "))}`;
  }
  return `${action}. ${sentence(note)}`;
}
