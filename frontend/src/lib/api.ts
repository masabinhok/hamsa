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
  source_kind: "news" | "official" | "fact_check";
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
  | { action: "publish"; checker: string; label?: Label; rationale_en?: string; rationale_ne?: string; note?: string }
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

async function call<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? response.statusText);
  }
  return response.json() as Promise<T>;
}

export const desk = {
  queue: (token: string) => call<DeskSummary[]>(token, "/desk/queue"),
  case: (token: string, id: string) => call<DeskCase>(token, `/desk/cases/${id}`),
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
