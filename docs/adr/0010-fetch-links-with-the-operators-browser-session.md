# 0010. Fetch pasted links with the operator's browser session

- Status: Accepted
- Date: 2026-10-14

## Context
Fact-checkers mostly receive links, not files: a reader pastes a Facebook, TikTok, X or YouTube link. Until now Hamsa stored the link but analysed only uploaded files, so a link-only report was judged on nothing. Facebook and TikTok serve video only to a logged-in session.

## Options considered
- **Platform OAuth.** Rejected: no platform API lets a logged-in user download other people's public posts. Facebook Login grants only the user's own content and the pages they manage; Meta Content Library and the TikTok Research API are approval-only programmes for vetted researchers; the X API is paid; the YouTube Data API has no download.
- **A browser extension for checkers** ("Send to Hamsa" from the page they are viewing). Uses their own session, but Facebook streams video in segments that an extension cannot reliably reassemble, and it is days of work for a second codebase.
- **yt-dlp with the operator's browser session.** Hamsa runs on the agency's own machine, so the worker can lend yt-dlp that machine's logged-in browser (`--cookies-from-browser`).

## Decision
The worker downloads the media behind a pasted link with yt-dlp (`backend/app/ingest/download.py`), borrowing the browser named in `FETCH_BROWSER`. YouTube refuses requests that carry browser cookies, so a failed try is repeated without them. The post's caption (yt-dlp's description or title) becomes the case text when the submitter typed none, because for a link the caption is the claim. Files are stored like uploads, so duplicate merging, media matching and the desk work unchanged.

## Consequences
- A link to a private or deleted post cannot be fetched. The case goes on with its text, and the public report page asks the submitter to send the file.
- The fetch uses a real person's login. Platforms' terms discourage automated downloads; the volume is one post per report, the same as a checker saving it by hand, and the agency decides whose browser to use.
- Applying to Meta Content Library and the TikTok Research API is future work: approved access would replace the browser session for those platforms.
