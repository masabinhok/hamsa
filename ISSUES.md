# Issues and product notes

Field notes from using Hamsa with six posts sent through the Telegram bot. These
notes cover correctness, evidence quality, ingestion, workflow, trust, and
polish.

## October 2026 field test

### Summary

- Six posts were submitted.
- Four were marked **false** through quick check.
- Two were routed to **needs a checker**.
- One of the six was a true positive, but the cited sources were too numerous
  and mostly irrelevant.
- At least one was a false negative: Hamsa relied on an unrelated post to mark
  a genuine video false. The video was a mix of Nepal flood clips with music.

The main issue is not only the verdict. Hamsa must explain the verdict with
evidence that actually matches the footage and the post's context.

### 1. Evidence relevance and source selection

- Sources cited for a video should match the footage or its context.
- Hamsa should not cite an unrelated fact check merely because it contains
  similar keywords.
- A source should be selected for relevance to the specific claim, not just
  because it exists in Hamsa's archive.
- Hamsa should be able to fetch relevant new or historical sources from the web
  when its local data is insufficient.
- Fact-check sources could be exposed as a separate feature: previously
  debunked claims from reputable fact-checking sites could be verified and
  returned quickly to the person who submitted the link.
- The current draft verdicts are repetitive and often unhelpful. They should
  explain the actual finding and cite sources a checker can trust.

### 2. Post context and captions

Hamsa appears to miss the caption or surrounding text of some posts. The media
alone is not enough to determine whether recycled footage is misleading.

- Fetch the post caption and use it as context.
- Preserve the publication date and use it when no explicit context is
  available.
- Consider what was known to have happened before the publication date, within
  a bounded time range.
- A genuine old video can still be true when resurfaced with the correct
  historical context. Recycled media should not automatically be marked false.
- A post about flooding in Nepal on August 27, for example, may be true even
  if it does not mention a specific later-identified flood such as Rasuwa.

### 3. Archive quality and evaluation data

- One recent Budhi Gandaki flood post was marked false with 97% confidence
  based on an archived source with no matching frame.
- One likely AI-generated Rasuwa flash-flood post was marked false using a
  source that was entirely out of context.
- The same Alt News article was cited repeatedly:
  [Nepal floods: unrelated videos of past disasters and AI visuals falsely
  viral](https://www.altnews.in/nepal-floods-unrelated-videos-of-past-disasters-ai-visuals-falsely-viral/).
- The current archive is too limited to support high-confidence conclusions.
  A small archive can mislead the model into treating the nearest match as
  proof.
- The current evaluation set appears too narrow: it contains only a handful
  of August flash-flood examples. It should not be treated as evidence that
  Hamsa generalizes to future events.

Questions to resolve:

1. Do we need a local archive for the first useful version?
2. If we keep one, how do we communicate coverage limits and avoid
   overconfident matches?
3. Should archive matching be separated from live web research and from
   previously published fact-check lookup?
4. How can the evaluation set be expanded while keeping ground truth
   independent from the pipeline's own archive?

### 4. Incorrect recycled-media matches

A real flood photo was marked false with 90% confidence because it matched an
archived 2015 earthquake image:

> Second earthquake, dust over destroyed buildings, Nepal, 12 May 2015:
> Dust rises from destroyed buildings after second earthquake hits Nepal.

This is a serious failure mode. A visual match must also pass a contextual
check before it can affect the verdict. In this case, the post should have
been published as true after a checker edited the draft.

### 5. Media retrieval failures

Hamsa did not bring the following Facebook post to the desk:

<https://www.facebook.com/mteverestfacts/posts/pfbid02fCXbgMqkFB4ZGNM5FFhafNtGouEFDPgLHE2JaHTt8G4wHE4sUSHVRDhkFgeetr4Xl>

The same link involved a sensitive video that required permission to view.
This is a real platform limitation, not necessarily a pipeline bug.

Potential fallback:

- Ask for the link first.
- If Hamsa cannot retrieve the media, ask the user to upload the image or
  video through the website.
- Make retrieval failure explicit to the checker instead of silently producing
  an evidence-based verdict from an archive match.

### 6. Duplicate links and duplicate media

If the same link is submitted again, Hamsa should reuse the prior pipeline
result where safe. If the same media appears at a different link, perceptual
matching should identify it and reuse relevant prior knowledge.

The distinction to investigate:

- Same link: pipeline/cache concern.
- Same media at a different link: media fingerprinting and evidence-reuse
  concern.

## October 22 ideas

### 7. English editing with Nepali translation

When a checker edits a draft verdict, they should be able to write in English
and have the final explanation automatically translated into Nepali.

The checker must still review the translated result before publishing.

## October 23 ideas

### 8. Readability and submission flow

- Review the UI for readability and increase text sizes if necessary.
- Ask users for a link first; uploading a video is tedious.
- Offer media upload on the website only for cases where Hamsa cannot retrieve
  the media.
- Add clear interaction feedback. For example, copying a frame should show a
  visible success state so the user knows the action worked.
- Apply subtle, consistent interaction animations across the desk without
  distracting from the evidence.

### 9. Deployment and SEO

Investigate deployment targets:

- `hamsa.vercel.app`
- `hamsa.sabinshrestha69.com.np`

Add basic SEO once the public deployment and product positioning are stable.

### 10. Mobile client

Assess whether a mobile client can reuse the existing backend. Do not start
this before the core web workflow is reliable.

### 11. Checker identity and accountability

Typing an arbitrary checker name does not provide accountability. Consider:

- An administrator who creates accounts for fact-checking employees.
- A verified identity for every checker.
- An audit trail of who reviewed, edited, and published a verdict.
- A public checker profile or organization identity on published reports.
- Clear distinction between an AI draft and a human-approved verdict.

The workflow should improve trust without exposing private staff information.

### 12. Screenshot cropping

Investigate automatic cropping or content-region detection for screenshots.
App chrome, icons, timestamps, and backgrounds can interfere with visual
matching. Cropping must preserve useful context and should be shown to the
checker before it is used as evidence.

### 13. Logo and visual identity

Explore a premium Hamsa/swan logo and an SVG version. The mark should remain
legible at small sizes and fit the existing visual language.

### 14. Reverse-image search

![A genuine video claimed false](image.png)

Investigate whether Hamsa should perform reverse-image or reverse-video search
for keyframes. A genuine video was found elsewhere after Hamsa claimed it was
false, so external search could provide an important counter-signal.

### 15. AI-generated media analysis

Investigate whether Hamsa can identify likely AI-generated images or videos.
This must be treated as supporting evidence, not proof. Missing metadata or
weak forensic signals should result in an inconclusive result rather than a
confident verdict.

A possible analysis contract is below:

```text
You are the core analysis engine for a professional fact-checking application.
Evaluate whether an image or video is likely AI-generated, manipulated, or
authentic using only the telemetry and metadata provided.

Analyze these dimensions:

1. Provenance and watermarks
   - Check for C2PA Content Credentials.
   - If present, extract and verify the signing entity and edit history.
   - Check for known invisible-watermark signals such as SynthID or Adobe
     Content Credentials.

2. Metadata integrity
   - Review EXIF and XMP metadata.
   - Look for generative-software signatures, structural anomalies, or missing
     metadata.
   - Missing camera metadata is not proof of generation.

3. Forensic and contextual signals
   - Evaluate supplied artifact scans, frame inconsistencies, asymmetric noise,
     blending anomalies, and unnatural rendering.
   - Cross-reference keyframes with supplied reverse-image-search results and
     known synthetic templates.

Return valid JSON with this schema:
{
  "is_ai_generated": "true | false | inconclusive",
  "confidence_score": 0.0,
  "primary_evidence": ["string"],
  "provenance_status": "string",
  "user_friendly_summary": "string"
}

Do not guess or hallucinate. If signals are missing or inconclusive, return
"inconclusive", lower the confidence score, and explain what evidence is
missing. This assessment must not override contextual evidence or human review.
```

## Proposed order of work

1. Fix evidence relevance and prevent unrelated archive matches from driving a
   verdict.
2. Retrieve captions, publication dates, and available post context.
3. Make retrieval failures explicit and add a website media-upload fallback.
4. Separate archive matching, live web research, and prior-fact-check lookup.
5. Expand the independent evaluation set and calibrate confidence.
6. Add duplicate-link and duplicate-media handling.
7. Add checker identity, audit history, and reviewed translation.
8. Improve readability, interaction feedback, and the end-to-end demo flow.
9. Revisit deployment, SEO, mobile, logo, and AI-media analysis after the core
   fact-checking workflow is reliable.

The central success criterion is not that Hamsa always produces a verdict. It
is that Hamsa gives a checker a relevant, explainable, appropriately
calibrated result—or clearly says when it does not have enough evidence.
