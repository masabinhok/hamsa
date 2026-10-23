// Typed client for the Hamsa API. Shapes mirror backend/app/api/schemas.py and the
// stage contracts in backend/app/pipeline/contracts.py.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Route = "merge" | "dismiss" | "fast_track" | "human_review" | "investigate";
export type Label = "false" | "misleading" | "true" | "unverifiable";
export type Stance = "supports" | "refutes";

export interface DeskSummary {
  id: string;
  created_at: string;
  route: Route | null;
  reasons: string[];
  proposed_label: Label | null;
  claim_en: string | null;
  text: string | null;
  media_count: number;
}

export interface Claim {
  claim: string;
  claim_en: string;
  places: string[];
  claimed_date: string | null;
  numbers: { value: number; unit: string | null; refers_to: string }[];
  visible_text: string[];
  watermarks: string[];
  handles: string[];
  checkable: boolean;
}

export interface ArchiveHit {
  archive_id: string;
  frame_index: number;
  phash_distance: number | null;
  cosine: number | null;
  inliers: number | null;
  post_seconds: number | null;
  archive_seconds: number | null;
  archive_label: "prior" | "verified_genuine";
  original_context: string;
  original_date: string | null;
  source_url: string;
}

export interface Passage {
  passage_id: string;
  source: string;
  source_kind: "news" | "official" | "fact_check" | "web";
  url: string;
  title: string | null;
  published_at: string | null;
  text: string;
  score: number;
}

export interface Verdict {
  label: Label;
  confidence: number;
  rationale_en: string;
  rationale_ne: string;
  citations: { passage_id: string; stance: Stance }[];
  // Null on verdicts drafted before findings were asked for.
  media_finding?: string | null;
  event_finding?: string | null;
  number_finding?: string | null;
  model: string;
  fallback: boolean;
}

export interface Outputs {
  failures: { stage: string; error: string; transient: boolean }[];
  claim: Claim | null;
  media_match: { hits: ArchiveHit[] } | null;
  evidence: { passages: Passage[] } | null;
  verdict: Verdict | null;
}

export type CaseStatus = "received" | "processing" | "routed" | "merged" | "published" | "rejected";

export interface DeskEvent {
  at: string;
  actor: string;
  from_status: string | null;
  to_status: string;
  note: string | null;
}

export interface DeskCase extends DeskSummary {
  status: CaseStatus;
  source_url: string | null;
  media: string[];
  outputs: Outputs | null;
  seconds: Record<string, number> | null;
  final_label: Label | null;
  events: DeskEvent[];
}

export type Decision =
  | {
      action: "publish";
      checker: string;
      label?: Label;
      rationale_en?: string;
      rationale_ne?: string;
      note?: string;
      // Where the checker found the original footage; Hamsa then recognises its reposts.
      original_url?: string;
    }
  | { action: "reject"; checker: string; note: string }
  | { action: "reopen"; checker: string; note: string };

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? response.statusText);
  }
  return response.json() as Promise<T>;
}

function call<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  return request<T>(path, { ...init, headers: { ...init.headers, Authorization: `Bearer ${token}` } });
}

export interface PublishedVerdict {
  label: Label;
  rationale_en: string;
  rationale_ne: string;
  sources: { name: string; url: string; stance: Stance }[];
  published_at: string;
  claim: Pick<Claim, "claim" | "claim_en" | "places" | "claimed_date"> | null;
  earlier_footage: Pick<ArchiveHit, "archive_label" | "original_context" | "original_date" | "source_url">[];
  media: string[];
}

export interface PublicCase {
  id: string;
  status: CaseStatus;
  created_at: string;
  text: string | null;
  source_url: string | null;
  media_count: number;
  // Status changes only: who decided and why stay on the desk.
  timeline: { at: string; status: CaseStatus }[];
  merged_into: string | null;
  verdict: PublishedVerdict | null;
  needs_media: boolean;
}

// The public side: anyone can submit a post and follow its verdict, no sign-in.
export const site = {
  submit: (form: FormData) => request<{ id: string }>("/cases", { method: "POST", body: form }),
  case: (id: string) => request<PublicCase>(`/cases/${encodeURIComponent(id)}`),
  // The file behind a link the worker could not open; the same report is checked again.
  sendMedia: (id: string, form: FormData) =>
    request<PublicCase>(`/cases/${encodeURIComponent(id)}/media`, { method: "POST", body: form }),
  verdicts: () => request<PublicCase[]>("/verdicts"),
  // Served only once a checker has published the report.
  mediaUrl: (id: string, name: string) =>
    `${API_URL}/cases/${encodeURIComponent(id)}/media/${encodeURIComponent(name)}`,
};

export const desk = {
  // Whose access code this is; null for the operator token, which names nobody.
  me: (token: string) => call<{ name: string | null }>(token, "/desk/me"),
  queue: (token: string) => call<DeskSummary[]>(token, "/desk/queue"),
  case: (token: string, id: string) => call<DeskCase>(token, `/desk/cases/${id}`),
  // Nepali for a checker's English rationale; `issue` says why to reread it, if anything.
  translate: (token: string, english: string) =>
    call<{ nepali: string; issue: string | null }>(token, "/desk/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ english }),
    }),
  decide: (token: string, id: string, decision: Decision) =>
    call<DeskCase>(token, `/desk/cases/${id}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(decision),
    }),
  // A desk path such as /desk/cases/{id}/media/{name} or /desk/cases/{id}/archive/{archive_id}.
  file: async (token: string, path: string): Promise<Blob> => {
    const response = await fetch(`${API_URL}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new ApiError(response.status, "media unavailable");
    return response.blob();
  },
};
