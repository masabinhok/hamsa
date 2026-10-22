# Live batch 01 (collected 2026-10-22)

Real posts for the `live` eval split. **Expected** is the label the cited source supports. The checker's published label on the desk is the ground truth, so these can be overruled. None of these posts or fact-checks are in `items.csv` or `drafts.csv`.

How they reach Hamsa: submitted as links to `POST /cases` (the same link pipeline the Telegram bot uses).

## False or misleading (rated by a fact-checker)

| # | Link | Platform | Expected | Source of the rating | What the footage really is | Tests |
|---|---|---|---|---|---|---|
| L01 | https://www.instagram.com/reel/DctJ8YSyhTe/ | Instagram | false | [BOOM, 1 Sep 2026](https://www.boomlive.in/fact-check/old-unrelated-videos-from-india-falsely-linked-to-nepal-floods-32180) | Bhatghar Dam, Pune, India | foreign footage, caption about a different topic (Gandak barrage) |
| L02 | https://www.instagram.com/reel/Dco5R5Pzq5S/ | Instagram | false | same BOOM article | staged clip from Vrindavan, India, online since July 2026 | Instagram fetch failure (yt-dlp gives HTTP 400) |
| L03 | https://www.tiktok.com/@kickbackmedia/video/7678453828554886413 | TikTok | false | [Newschecker Nepal, 28 Aug 2026](https://nepal.newschecker.co/en/english/2025-video-from-uttarakhand-falsely-shared-as-recent-bhotekoshi-flash-flood-in-nepal) | Dharali, Uttarakhand flash flood, 5 Aug 2025 | recycled footage with on-screen figures ("hundreds dead, 1,000+ missing") |
| L04 | https://www.facebook.com/reel/1075308675354455 | Facebook | false | same Newschecker article | same Dharali footage | the same clip on another platform: duplicate or archive match |
| L05 | https://www.tiktok.com/@kuberneupane25/video/7123189596627733787 | TikTok | false | [Newschecker Nepal, 10 Aug 2022](https://nepal.newschecker.co/en/english/old-videos-showing-floods-in-indias-uttarakhand-and-nepals-mugu-falsely-shared-as-recent) | building collapsing into the Ganga, Uttarkashi, India, June 2013 | a 2022 post: older event, Nepali caption |
| L06 | https://www.tiktok.com/@dilliramtiwari3/video/7127306598313250074 | TikTok | misleading | same 2022 Newschecker article ("False Context") | real Mugu, Nepal flood, but from Sep 2019, shared as 2022 | genuine Nepal footage with the wrong date |
| L07 | https://fb.watch/iZNX3Zh7ej/ | Facebook | misleading | [Fact Crescendo explainer, 2 Mar 2023](https://srilanka.factcrescendo.com/english/a-viral-video-of-an-avalanche-in-nepal-understanding-the-phenomenon) | real 2021 avalanche at Kapuche Glacier Lake, sold as an "unseen first-ever cloud avalanche on Everest" | real footage, exaggerated framing; not a flood |
| L08 | https://www.tiktok.com/@sameer_ever1/video/7265704258912210177 | TikTok | misleading | [Newschecker Nepal, 16 Aug 2023](https://nepal.newschecker.co/en/english/fact-check-truck-swept-away-by-recent-floods-in-nepal-no-viral-video-is-from-manali-india) ("Missing Context") | Manali, Himachal Pradesh flood, Jul–Aug 2023 | TikTok blocked on this network: the could-not-open path |
| L09 | https://www.tiktok.com/@shree.5sarkar/video/7419656772408986900 | TikTok | misleading | [Newschecker Nepal, 30 Sep 2024](https://nepal.newschecker.co/fact-check-ne/nepal-kathmandu-flood-claim) | Atami, Japan landslide, 3 Jul 2021 | blocked here too; Nepali caption |
| L10 | https://www.tiktok.com/@sheralisherry4/video/7268303655302876417 | TikTok | misleading | [Newschecker Nepal, 23 Aug 2023](https://nepal.newschecker.co/fact-check-ne/landslides-floods-claim) | 2015 Gorkha earthquake clips sold as 2023 floods | blocked here too; earthquake footage that the archive holds |

## True (footage published by an established outlet, about the event it names)

| # | Link | Outlet | Posted | Event | Tests |
|---|---|---|---|---|---|
| L11 | https://www.youtube.com/shorts/eqmhYg69l2Q | CNA | 11 Oct 2026 | Budhi Gandaki flash flood | a recent event outside the August floods |
| L12 | https://www.youtube.com/watch?v=EmM79Xzvbg0 | NDTV | 29 Sep 2026 | Himlung avalanche ("4 dead, 12 missing") | figures that later rose to 15 dead: judged as of the post's date |
| L13 | https://www.youtube.com/shorts/61ap1qDXCtM | CNA | 29 Sep 2026 | Himlung avalanche ("2 dead, 14 missing") | same event, different early figures |
| L14 | https://www.youtube.com/shorts/gsXZ4JyFiJM | Firstpost | 28 Sep 2026 | Himlung avalanche | avalanche, not flood |
| L15 | https://www.youtube.com/watch?v=LoUJkrOmLLA | NewsX World | 3 Oct 2026 | Himlung avalanche ("15 workers killed") | the later figure |
| L16 | https://www.youtube.com/watch?v=hJpIyC0UR0A | Sky News | 30 Aug 2026 | Nepal–Tibet floods ("thousands missing") | true while an exaggerated version (L22) is not |
| L17 | https://www.youtube.com/watch?v=DEhKvXlCpOc | Business Standard | 27 Aug 2026 | Rasuwa flood explainer | explainer, not a single claim |
| L18 | https://www.youtube.com/watch?v=ug-6R5Fve2M | Kantipur TV HD | 26 Aug 2026 | Rasuwa, Nuwakot, Dhading damage | Nepali-language, long video |
| L19 | https://www.youtube.com/watch?v=8EwtfmzKdGc | Kantipur | 10 Jul 2025 | **July 2025** Bhotekoshi flood, Timure to Rasuwagadhi | genuine footage of an *earlier* flood on the same river: must not be called recycled 2026 footage |
| L20 | https://www.youtube.com/watch?v=3rd7YqacD6w | ET Now | 29 Sep 2024 | September 2024 Kathmandu floods (60+ dead) | a 2024 event, judged against 2024 reports |
| L21 | https://www.youtube.com/watch?v=ufaR0pMQoIY | NEWS9 Live | 28 Sep 2024 | September 2024 floods ("34 dead in Kathmandu Valley") | same event, figures |

## Needs the checker's call

| # | Link | Channel | Posted | Why it is uncertain |
|---|---|---|---|---|
| L22 | https://www.youtube.com/watch?v=AjcN5snc27g | Saptarangi Online | 15 Sep 2026 | "Tens of Thousands Missing, Dozens of Towns Swept Away". Reports from around that date counted about 5,000 missing, so likely false on the figures; the footage is unverified |
| L23 | https://www.youtube.com/watch?v=j4mnpRnbqTA | Suresh Pangeni | 12 Oct 2026 | "Massive Flood in Gorkha, Nepal 2083": likely genuine Budhi Gandaki footage from an individual channel; tests the Bikram Sambat year |

## Not included
- Fact-checks whose posts survive only as archive.today links (Wayanad, Atami TikTok mirrors): Hamsa cannot open an archive page as the post.
- The Philippines boats TikTok (Newschecker, 30 Sep 2024): removed.
- The Sochfactcheck elephant and CyberPeace compilation: already in the eval set.
