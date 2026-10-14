# 0011. The archive learns from verdicts, not from bulk downloads or web search

- Status: Accepted
- Date: 2026-10-14

## Context
Media matching is only as good as the archive. Until now the archive was 37 clips collected by hand, which does not scale to the next disaster and fills a laptop with other people's videos. The owner wanted the archive to grow as cases arrive.

## Options considered
- **Bulk collection in advance.** Rejected: unbounded storage, and it misses what goes viral next.
- **Search the web when a case arrives.** Built and measured on 2026-10-14: the claim's words, its on-screen text, and descriptions of the scene were searched on YouTube, and up to five short 360p candidates per case were downloaded and verified with the archive matcher. It recovered **0 of 9** recycled originals in the eval set, at 4 to 65 seconds per case. The originals of viral fakes are mostly on Instagram, TikTok, Facebook and X, which cannot be searched; a post's words describe the false claim, not the footage; and true reverse image search (Google Lens, TinEye, Bing Visual Search) has no free API.
- **Learn from the checkers' own work.** Checkers already find originals by hand, with the desk's copy-frame button and Google Lens. Hamsa only had to remember what they find.

## Decision
Every published verdict becomes a lesson (`lessons` table), which the worker works through when idle (`teach` in `backend/app/learn.py`):
- footage published as **true** is archived as `verified_genuine`, dated by the report;
- footage published as **false or misleading** is archived as known debunked footage (`prior`), with the published rationale as its context;
- the **original a checker found**, pasted into the desk's "Original found at" field, is downloaded and archived as `prior`, dated by its upload.

Only keyframes, their fingerprints and a link are kept, not the video. Footage byte-identical to an eval post never enters the archive. The verdict prompt now states that a strong archive match is evidence in its own right, even though no passage repeats it.

## Consequences
- Checked end to end on 2026-10-14: a repost of footage nobody had seen went to a human; after it was published as false with the original's link, a second repost (mirrored, cropped, captioned) matched both lessons (310 and 59 ORB inliers) and was judged false at 0.90 to 0.93.
- The first report of new footage still needs a human; every later repost does not.
- A verdict later reopened and corrected leaves its lesson in the archive; removing it is manual for now.
