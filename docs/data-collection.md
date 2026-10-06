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

1. **Start from a fact-check** in [`data/eval/sources.md`](../data/eval/sources.md). One article often covers several posts.
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

`false` versus `misleading`: **false** means the core claim is wrong (the video is not from Nepal). **Misleading** means real elements are framed to mislead (real Nepal footage, wrong date or wrong death toll).

## Rules

- **Label what is true, not what you think Hamsa will say.**
- **When unsure, write it in `notes` and use `unverifiable`.** Never guess a label.
- **Media stays local.** `data/eval/media/` is gitignored because these are other people's posts. Only labels and links are committed.
- **Skip posts that expose private people**, such as identifiable children or victims' personal details, unless the media is already widely published by news outlets.
- **Hold out a test split.** We tune on `h001` to `h040` and report final numbers on `h041` onward, which we will not look at while tuning.
