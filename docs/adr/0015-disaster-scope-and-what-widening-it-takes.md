# 0015. Stay scoped to disasters; widening the scope is a corpus and prompt change, not a rebuild

- Status: Accepted
- Date: 2026-10-23

## Context
The owner sees a bigger product: the public forwards any suspicious post and gets a quick answer, with disasters as only the first topic. Before demo day the question is whether to widen Hamsa now, and what widening would cost later.

## Options considered
- **Widen now** to politics, health and other topics. Rejected: every threshold and rule in the router was tuned and checked on disaster posts (the August eval set and 37 live posts). On other topics there is no labelled data, so a wrong fast-track could not even be measured, and a wrong fast-track is the costliest error Hamsa can make.
- **Stay scoped, and keep the parts that are disaster-specific few and named.**

## Decision
Hamsa stays a disaster misinformation desk for Nepal. Only these parts know about disasters:
- the corpus filter, `mentions_disaster` in `backend/app/corpus/fetch.py` (Nepali and English disaster terms), which decides which news is stored; fact-checks are stored whatever their topic;
- the first lines of the extraction and verdict prompts (`backend/app/pipeline/extract.py`, `verdict.py`), which say the posts are about disasters in Nepal;
- the eval data.

Everything else is topic-free: link and file intake, keyframes, media matching against the archive, ClaimReview and web search, the router's rules, the repeat detection, the desk, and the Telegram and web channels.

## Consequences
- Widening to a new topic means: a corpus filter (or none) for that topic, prompt wording, and a labelled set of that topic's posts to check the router against before any fast-track is trusted. No pipeline stage, contract or table changes.
- A newsroom such as Techpana can run one Hamsa per desk (disasters, elections) on the same code, each with its own corpus and archive.
