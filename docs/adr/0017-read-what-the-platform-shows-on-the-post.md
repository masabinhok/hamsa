# 0017. Read what the platform shows on the post: X Community Notes and TikTok's AI label

- Status: Accepted
- Date: 2026-10-25

## Context
A post the desk published as "true" was a compilation of old, unrelated flood clips. X was already showing a Community Note on it ("Readers added context: the video compiles clips from prior unrelated mudslide/flood incidents…", citing AAP FactCheck, The Guardian and Reuters). TikTok, for its part, labels videos that the creator or TikTok marks as AI-generated. Hamsa downloaded both posts and read neither signal: yt-dlp drops them.

## Options considered
- **The X API.** Paid, and per-post note lookup is not part of the free tier.
- **The Community Notes data download.** Public, but it needs an X login to fetch, ships as large daily TSVs, and is about all notes rather than the one post in hand; shown-or-not depends on rating data we would have to recompute.
- **What the platform's own public page shows.** X's embed endpoint (`cdn.syndication.twimg.com/tweet-result`, the one embedded tweets use) returns the note displayed on a post, with its source links, without a login. TikTok's post page carries `IsAigc` and `AIGCDescription` in its embedded data.

## Decision
`on_post` in `backend/app/pipeline/platform.py` reads both from the post's own link and adds them as evidence of a new kind, `platform`, ahead of the corpus passages (`add_on_post` in `backend/app/pipeline/run.py`). The note's t.co links are expanded by reading their redirect only; Hamsa never fetches the targets. Any failure gives no signal, never a failed case.

The router treats them conservatively (`backend/app/router/route.py`):
- a `true` draft on a post carrying an X note goes to a checker ("X readers added context to this post");
- TikTok's AI label counts like a visible AI-tool watermark, so the existing watermark rule applies;
- neither is ever an independent source for a fast-track.

## Consequences
- Measured on 2026-10-25: 2 of 12 X posts in the database carry a visible note, one of them the case above; the TikTok demo post (L03) has no AI label.
- The X endpoint is undocumented. It returns the note only when a `token` parameter is present (its value is not checked today). If X changes it, cases simply get no note.
- The labelled eval passes no post links to the pipeline, so its numbers are unaffected; the signal is measured on the live split (`python -m app.eval.live --fresh`).
- Notes appear hours after a post goes viral, so the signal helps most for posts reported later, and for repeats checked again.
