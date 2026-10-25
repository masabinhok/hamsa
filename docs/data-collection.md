# Eval data collection

The eval set is how we know Hamsa works. Every pipeline change is scored against it, and its numbers go in the README. A small set labelled carefully beats a large set labelled carelessly.

## What we are building

About **60 posts** from the August 2026 floods, each with a ground-truth label, plus the **original media** behind every recycled post (those originals also seed the media-match archive).

| Bucket | Target | Why it matters |
|---|---|---|
| Recycled (old or foreign footage passed off as Nepal 2026) | 20 | Hamsa's strongest signal; measures media-match recall |
| Synthetic (AI-generated video or images) | 10 | A large share of real flood fakes; measures how far provenance and evidence get without pixel detection |
| Miscaptioned, edited, fabricated text | 10 | Claim-level reasoning, not media matching |
| **True** (genuine footage, correctly captioned) | 15 | Without these we cannot measure false alarms |
| Unverifiable | 5 | The router must send these to a human, not guess |

The true posts are as important as the fakes. A system that calls everything fake scores 100% on fakes and is useless.

## Workflow per item (10 to 15 minutes)

1. **Start from a fact-check** published by Nepal Factcheck, Newschecker Nepal, Techpana, AFP, BOOM or another published fact-checker; `fact_check_url` in `items.csv` records which. One article often covers several posts.
2. **Find the post itself.** Fact-checks usually show a screenshot or link. Search the claim text on Facebook or TikTok if the link is dead.
3. **Archive it** at [archive.ph](https://archive.ph) or [web.archive.org/save](https://web.archive.org/save) and keep the archive URL. Posts get deleted.
4. **Download the media** as `data/eval/media/h001.mp4` (or `.jpg`). For video: `yt-dlp -o "data/eval/media/h001.%(ext)s" <url>`. If the post is gone, use the fact-check's screenshot or keyframe.
5. **For recycled items, get the original too**, as `h001_orig.mp4`, and note what it really shows: event, place, year.
6. **Fill one row** in `data/eval/items.csv` (any spreadsheet app; save as CSV, UTF-8).
7. **Validate:** `cd backend && uv run python -m app.eval.validate`. It lists every problem with its line number.

For **true** items, collect genuine flood footage that a credible outlet published or confirmed (Kathmandu Post, Onlinekhabar, Setopati, Kantipur, Nepal Police, Nepal Army, NDRRMA), and cite that outlet in `evidence_urls`.

## Column reference

| Column | Required | Notes |
|---|---|---|
| `id` | yes | `h001`, `h002`, ... never reused |
| `kind` | yes | `image`, `video`, `text` |
| `platform` | yes | `facebook`, `tiktok`, `x`, `youtube`, `instagram`, `telegram`, `whatsapp`, `news_site`, `other` |
| `language` | yes | `ne`, `en`, `mixed`, `other` |
| `claim_text` | yes | The claim exactly as posted, in its original language |
| `claim_text_en` | no | Your English translation |
| `post_url` | one of three | Original post link |
| `post_archive_url` | one of three | archive.ph or Wayback link |
| `posted_on` | no | `YYYY-MM-DD` |
| `media_file` | if image/video | File name in `data/eval/media/` |
| `verdict` | yes | `false`, `misleading`, `true`, `unverifiable` |
| `tactic` | yes | `recycled`, `miscaptioned`, `edited`, `synthetic`, `fabricated_text`, `none` (true posts only) |
| `original_source_url` | if recycled | Where the footage really comes from |
| `original_context` | if recycled | e.g. `2023 Himachal Pradesh floods, Kullu` |
| `original_media_file` | no | e.g. `h001_orig.mp4` |
| `fact_check_url` | one of two | Published fact-check |
| `evidence_urls` | one of two | Several URLs separated by `|` |
| `notes` | no | Anything a reviewer should know, e.g. visible watermark, uploader is an AI-content page |

`false` versus `misleading`: **use the fact-checker's own published rating.** Fact-checkers differ: Nepal Factcheck rates foreign footage passed off as Nepal as भ्रामक (misleading), while AFP usually rates the same pattern false. Hamsa is measured on agreement with published fact-checks, so the label follows the publisher. The scorer reports exact-label agreement and, separately, whether Hamsa refuted the post at all (false or misleading versus true or unverifiable), which is what matters for triage. For items with no fact-check (true posts, your own finds): **false** means the core claim is wrong; **misleading** means real elements framed to mislead.

## Rules

- **Label what is true, not what you think Hamsa will say.**
- **When unsure, write it in `notes` and use `unverifiable`.** Never guess a label.
- **Media stays local.** `data/eval/media/` is gitignored because these are other people's posts. Only labels and links are committed.
- **Skip posts that expose private people**, such as identifiable children or victims' personal details, unless the media is already widely published by news outlets.
- **Hold out a test split.** We tune on `h001` to `h040` and report final numbers on `h041` onward, which we will not look at while tuning.

## The media archive

Media matching compares submitted posts against an archive of footage with a known origin. The archive builds itself from two places:

1. **Originals of recycled eval items.** If a row has `tactic=recycled` and `original_media_file`, the original goes into the archive as `prior` footage automatically. Nothing extra to do.
2. **`data/archive/manifest.csv`** for everything else. Put files in `data/archive/media/` (gitignored) and add a row:

| Column | Notes |
|---|---|
| `archive_id` | lowercase with dashes, e.g. `kullu-flood-2023-bridge` |
| `media_file` | file name in `data/archive/media/` |
| `label` | `prior` (older or elsewhere) or `verified_genuine` (confirmed footage of a real event; fill `original_date`, because a repost more than 30 days later counts as recycled) |
| `original_context` | what it really shows, e.g. `2023 Himachal Pradesh floods, Kullu` |
| `original_date` | `YYYY-MM-DD` if known |
| `source_url` | where it was first published |

The quickest way is the collector, which downloads the clip, reads its title and upload date, and appends the row (it refuses eval posts and clips already archived):

```bash
cd backend
uv run python -m app.archive add "<url>" --label verified_genuine --context "Budhi Gandaki flash flood, Gorkha, 11 Oct 2026"
# add --date YYYY-MM-DD when the footage is older than the upload; --browser firefox for posts behind a login
```

When the build finds an archive clip that matches an eval post, it prints a `check:` line. Genuine footage archived before its reposts is realistic, but decide per pair whether it makes the eval too easy.

Worth adding: **verified genuine flood footage** from news outlets and official pages (so real posts can be confirmed, not just fakes debunked), and **well-known older disaster clips** that tend to resurface (Kullu 2023, Melamchi 2021, Kerala 2018, the Columbia Glacier videos).

Then rebuild: `cd backend && uv run python -m app.archive` (Qdrant must be running: `docker compose up -d`).

**Never put eval posts themselves in the archive.** The archive is what Hamsa knows beforehand. A post matching itself proves nothing.
