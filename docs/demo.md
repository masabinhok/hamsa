# Demo script: sender → checker → sender

About 5 minutes. One real fake, one real genuine post, and a repeat, all on one laptop.

## Before you record

1. **A clean desk, the same archive.** Stop the stack, keep `data/hamsa.db` aside, and start with an empty database so every post is new: set `DATABASE_URL=sqlite:////app/data/demo.db` in `.env` and `docker compose --profile telegram up -d`. The archive (Qdrant and `data/archive/`) is untouched, so Hamsa still knows the footage it has seen. Put `DATABASE_URL` back afterwards.
2. **The posts** (all from `data/eval/live/`):
   - **The fake:** the TikTok of the 2025 Dharali (Uttarakhand) flash flood shared as Nepal's August floods, L03 `https://www.tiktok.com/@kickbackmedia/video/7678453828554886413`.
   - **Its repost:** the same clip on Facebook, L04 `https://www.facebook.com/reel/1075308675354455`.
   - **The genuine post:** Firstpost's Himlung avalanche short, L14 `https://www.youtube.com/shorts/gsXZ4JyFiJM` (not CNA's L11: its footage matches a case published in the main database, which the demo database does not have).
3. **Rehearse once, then reset:** the database (delete `data/demo.db` and restart), so the recording starts empty. Each new post takes 1–2 minutes, so record those waits and cut them, or send the fake a few minutes before you start talking.
4. **Screens:** your phone (Telegram, mirrored or filmed), the desk (`/desk`, signed in), and a second phone or account for the repost.

## Act 1: a reader is unsure (sender, 45 s)
*"A flood video is going round. Is it Nepal?"*
- On Telegram, forward the **fake** link to @hamsa_factcheck_bot.
- The bot answers at once: report number and a link. Open the link: the report page shows where the check has got to (received → checking → with the checkers).

## Act 2: the checker's desk (checker, 2 min)
- The case is at the top of the desk, marked for one-click publish: **"recycled media: matches Flash flood at Dharali village, Uttarkashi, Uttarakhand, India, 5 Aug 2025"**.
- Show the side-by-side: the post's frame next to the archived original, with its date and source.
- Show the findings under the draft (footage from elsewhere, event, figures) and the cited sources. Point out that every source is about this footage, not just about floods.
- Press **Edit wording** and change one sentence of the English rationale: the Nepali is redone by itself when you leave the box.
- Publish.

## Act 3: the reader gets the answer (sender, 30 s)
- The phone buzzes: the verdict in Nepali and English, with sources and the report link.
- The report page now shows the verdict, the claim, and the original footage.

## Act 4: the same clip again (second sender, 45 s)
- From the second phone, forward the **same TikTok link**: answered in seconds with the published verdict, with no model run and no checker. ("This post was checked before.")
- Forward the **Facebook repost** (a different file and platform): Hamsa matches its frames to the footage the checker just published and puts it on the desk for a one-click publish, citing **"same footage published as false on Hamsa"** (or the Dharali original, if the draft says misleading). The worker learns a published clip when it is idle, so leave a minute between Act 3 and this.

## Act 5: when Hamsa does not overclaim (checker, 45 s)
- Send the **genuine** Firstpost post. Hamsa drafts *true*, with reports of the Himlung avalanche, but sends it to a human: **"the event is confirmed but nothing shows the footage is from it"**. The checker decides.
- *"Hamsa never publishes on its own. It does the searching and matching a checker would do, and says how sure it is and why."*

## Close (30 s)
- Open-weight models only, on one laptop with an 8 GB GPU (README, AI usage disclosure).
- Numbers from real posts, not only the August set: `python -m app.eval.live` (README, Evaluation).
- Works over Telegram, Messenger and the web.

## If something fails on the day
- **Groq rate-limited:** the local fallback model drafts instead, and the case goes to a human; say so, since it shows the failure path.
- **A link won't open** (private post): the bot asks for the file; send it, and the same report updates. That's worth showing too.
- **Ollama killed for memory:** close Firefox, Discord and other heavy apps before recording; the vision model needs about 2 GB of RAM beyond the GPU.
