# 0013. Search the web for evidence about the event through self-hosted SearXNG

- Status: Accepted
- Date: 2026-10-22

## Context
The trusted corpus holds a handful of Nepali outlets. Real posts sent on 2026-10-21 made claims the corpus could not address. One was "403 tourists missing" after the Rasuwa flood: no corpus article counted tourists, so the verdict compared the figure with October reports on other floods and drafted "false". ADR 0011 rejected web search for finding a post's *footage*; this decision is about *text evidence* on the event and its figures, where a news search does work.

## Options considered
- **A hosted search API (Brave, Tavily).** Simple and stable, but each needs a key and an account. The case's claim text goes to a third party, and free quotas cap a busy day.
- **Scraping a search engine directly.** Fragile; engines block it within minutes.
- **Self-hosted SearXNG.** A metasearch server in the compose stack, bound to localhost, with a JSON API, no key and no quota. It queries several news engines and drops any that block it. It is a search service, not a model, so the open-weight rule (ADR 0001) is unaffected. The ranking is done by bge-m3, already used for retrieval.

## Decision
When `SEARXNG_URL` is set, the retrieval stage searches news for the English claim and its places (`backend/app/pipeline/web_search.py`). It fetches the top 6 pages and keeps a page only if two things hold:
- its own date falls inside the case's news window. Figures change daily, so undated pages are dropped.
- its best chunk scores bge-m3 cosine 0.6 or more against the claim.

Up to 2 such passages take the last of the 8 evidence slots as `source_kind = web`. Web pages are untrusted: the verdict prompt says to prefer a trusted passage, the desk labels them "web search, unvetted", and the router never counts them as independent sources for a fast-track.

## Consequences
- Each case's English claim reaches the news engines SearXNG queries; the search server itself runs locally.
- On three real claims, on-topic pages scored 0.67–0.76 and off-topic ones 0.25–0.37. For "403 tourists missing" it found "596 foreign tourists missing" (Business Insider, 28 Aug), the same-group figure from the post's week.
- An engine that blocks SearXNG (Google News did on the first query) just contributes nothing. A failed search leaves corpus evidence only.
- A web page can still be wrong. The verdict cites it, the checker sees which sources are unvetted, and nothing fast-tracks on web evidence alone.
